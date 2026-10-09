#!/usr/bin/env python3
"""
ASR-postcorrectie fine-tuning (SFT)
===================================

Fine-tunet een klein seq2seq-model (default mT5) om ruwe ASR-output te
corrigeren naar de door de arts goedgekeurde tekst. Input/target komen uit de
JSONL van `tools/build_training_data.py` (--only asr).

GEEN audio nodig - past binnen het privacybeleid (audio wordt verwijderd).

Vereisten (GPU-machine):
    pip install "transformers>=4.40" datasets accelerate sentencepiece torch

Gebruik:
    python -m services.learning.training.finetune_asr_correction \
        --data /data/training/asr_correction.jsonl \
        --base-model google/mt5-small \
        --output-dir /models/asr_corrector

Dit script draait NIET in de standaard VitaScribe-omgeving (geen torch); het is
bedoeld voor een aparte trainingsmachine. Evalueer het resultaat altijd tegen de
meetlat (shared/evaluation.py) vóór je het in productie neemt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ASR-postcorrectie SFT")
    ap.add_argument("--data", required=True, help="JSONL met {input,target}")
    ap.add_argument("--base-model", default="google/mt5-small")
    ap.add_argument("--output-dir", default="/models/asr_corrector")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--max-input", type=int, default=512)
    ap.add_argument("--max-target", type=int, default=512)
    ap.add_argument("--min-examples", type=int, default=200)
    args = ap.parse_args(argv)

    data = _load_jsonl(args.data)
    if len(data) < args.min_examples:
        print(
            f"Te weinig voorbeelden ({len(data)} < {args.min_examples}). "
            "Verzamel meer artsfeedback voordat je traint.",
            file=sys.stderr,
        )
        return 2

    # Zware imports pas hier (alleen op de trainingsmachine beschikbaar)
    try:
        from datasets import Dataset
        from transformers import (
            AutoModelForSeq2SeqLM,
            AutoTokenizer,
            DataCollatorForSeq2Seq,
            Seq2SeqTrainer,
            Seq2SeqTrainingArguments,
        )
    except Exception as e:
        print(f"Trainingsdependencies ontbreken: {e}\n"
              "Installeer: pip install transformers datasets accelerate sentencepiece torch",
              file=sys.stderr)
        return 1

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.base_model)

    # mT5 vaart wel bij een korte taakinstructie
    prefix = "corrigeer transcriptie: "

    def preprocess(batch):
        inputs = [prefix + x for x in batch["input"]]
        model_inputs = tokenizer(
            inputs, max_length=args.max_input, truncation=True
        )
        labels = tokenizer(
            text_target=batch["target"], max_length=args.max_target, truncation=True
        )
        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    ds = Dataset.from_list(data).map(
        preprocess, batched=True, remove_columns=["input", "target"]
    )
    split = ds.train_test_split(test_size=0.1, seed=42)

    collator = DataCollatorForSeq2Seq(tokenizer, model=model)
    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=20,
        predict_with_generate=True,
        fp16=True,
        report_to=[],
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=split["train"],
        eval_dataset=split["test"],
        data_collator=collator,
        tokenizer=tokenizer,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"Klaar. Model opgeslagen in {args.output_dir}")
    print("Evalueer nu tegen de meetlat (shared/evaluation.py) vóór productie.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
