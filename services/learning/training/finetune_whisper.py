#!/usr/bin/env python3
"""
Akoestische Whisper fine-tuning (OPTIONEEL, audio-retentie vereist)
===================================================================

Fine-tunet Whisper op (audio, gecorrigeerd transcript)-paren voor de beste
WER-winst op Nederlands/dialect en medische termen.

LET OP - privacy: het standaard VitaScribe-beleid VERWIJDERT audio na
goedkeuring. Dit script is dus alleen bruikbaar als je een expliciete,
toestemming-gedekte audio-retentie inricht voor trainingsdoeleinden (DPIA +
bewaartermijn + verwijderrecht). Zonder retentie: gebruik in plaats hiervan de
tekstgebaseerde ASR-postcorrectie (finetune_asr_correction.py), die geen audio
nodig heeft.

Input: een manifest-JSONL met regels {"audio_path": "...", "text": "..."}.

Vereisten (GPU-machine):
    pip install "transformers>=4.40" datasets accelerate jiwer librosa soundfile torch

Gebruik:
    python -m services.learning.training.finetune_whisper \
        --manifest /data/training/audio_manifest.jsonl \
        --base-model openai/whisper-large-v3 \
        --output-dir /models/whisper_nl_praktijk --language nl
"""

from __future__ import annotations

import argparse
import json
import sys


def _load_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Akoestische Whisper fine-tuning")
    ap.add_argument("--manifest", required=True, help="JSONL {audio_path,text}")
    ap.add_argument("--base-model", default="openai/whisper-large-v3")
    ap.add_argument("--output-dir", default="/models/whisper_nl_praktijk")
    ap.add_argument("--language", default="nl")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--min-examples", type=int, default=500)
    ap.add_argument("--i-have-consent-and-retention", action="store_true",
                    help="Bevestig expliciet dat audio-retentie AVG/NEN-conform is geregeld")
    args = ap.parse_args(argv)

    if not args.i_have_consent_and_retention:
        print(
            "GEBLOKKEERD: akoestische fine-tuning vereist bevestigde audio-retentie "
            "met toestemming (DPIA, bewaartermijn, verwijderrecht). Voeg "
            "--i-have-consent-and-retention toe als dit geregeld is, of gebruik de "
            "tekstgebaseerde ASR-postcorrectie zonder audio.",
            file=sys.stderr,
        )
        return 3

    data = _load_jsonl(args.manifest)
    if len(data) < args.min_examples:
        print(f"Te weinig voorbeelden ({len(data)} < {args.min_examples}).",
              file=sys.stderr)
        return 2

    try:
        import torch
        from datasets import Audio, Dataset
        from transformers import (
            WhisperForConditionalGeneration,
            WhisperProcessor,
            Seq2SeqTrainer,
            Seq2SeqTrainingArguments,
        )
    except Exception as e:
        print(f"Trainingsdependencies ontbreken: {e}", file=sys.stderr)
        return 1

    processor = WhisperProcessor.from_pretrained(args.base_model, language=args.language, task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(args.base_model)
    model.generation_config.language = args.language
    model.generation_config.task = "transcribe"

    ds = Dataset.from_list(data).cast_column("audio_path", Audio(sampling_rate=16000))

    def prepare(batch):
        audio = batch["audio_path"]
        batch["input_features"] = processor.feature_extractor(
            audio["array"], sampling_rate=16000
        ).input_features[0]
        batch["labels"] = processor.tokenizer(batch["text"]).input_ids
        return batch

    ds = ds.map(prepare, remove_columns=ds.column_names)
    split = ds.train_test_split(test_size=0.1, seed=42)

    class _Collator:
        def __call__(self, features):
            input_features = [{"input_features": f["input_features"]} for f in features]
            batch = processor.feature_extractor.pad(input_features, return_tensors="pt")
            label_features = [{"input_ids": f["labels"]} for f in features]
            labels_batch = processor.tokenizer.pad(label_features, return_tensors="pt")
            labels = labels_batch["input_ids"].masked_fill(
                labels_batch.attention_mask.ne(1), -100
            )
            batch["labels"] = labels
            return batch

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.lr,
        eval_strategy="epoch",
        save_strategy="epoch",
        fp16=torch.cuda.is_available(),
        logging_steps=20,
        report_to=[],
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=split["train"],
        eval_dataset=split["test"],
        data_collator=_Collator(),
        tokenizer=processor.feature_extractor,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    processor.save_pretrained(args.output_dir)
    print(f"Klaar. Model in {args.output_dir}. Evalueer WER tegen de meetlat vóór productie.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
