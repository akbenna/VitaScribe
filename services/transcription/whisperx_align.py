"""
WhisperX forced-alignment (Fase 3)
==================================

Optionele verfijning van woord-timestamps via wav2vec2 forced alignment
(WhisperX). Faster-Whisper geeft segment-gedreven timestamps die kunnen
"driften"; wav2vec2-alignment legt elk woord op een echte audiogrens. Dat maakt
de woord-niveau diarisatie (services/transcription/diarization_align.py) nóg
preciezer - vooral op sprekergrenzen midden in een segment.

Zwaar (extra model + GPU) en daarom standaard uit. Schakel in via
WHISPER_USE_FORCED_ALIGNMENT=true. Bij ontbrekende library of fout valt de
pipeline terug op de Faster-Whisper woord-timestamps.

De daadwerkelijke alignment (`forced_align`) vereist whisperx/torch en is niet
unit-getest; de pure mapper (`apply_aligned_words`) wel.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


def is_available() -> bool:
    """Is WhisperX geïnstalleerd?"""
    try:
        import whisperx  # noqa: F401
        return True
    except Exception:
        return False


def apply_aligned_words(
    whisper_segments: List[dict],
    aligned_segments: List[dict],
) -> List[dict]:
    """Vervang de woord-timestamps in whisper_segments door de uitgelijnde
    woorden uit een WhisperX-resultaat. Pure functie (geen IO/model).

    Args:
        whisper_segments: onze segmentdicts (met o.a. 'words').
        aligned_segments: WhisperX `result["segments"]`, elk met 'words'
            [{"word","start","end","score"}].

    Mapping gebeurt op segmentindex (WhisperX behoudt de volgorde). Segmenten
    zonder bruikbare alignment behouden hun bestaande woorden.
    """
    if not aligned_segments:
        return whisper_segments

    for i, seg in enumerate(whisper_segments):
        if i >= len(aligned_segments):
            break
        aligned_words = aligned_segments[i].get("words") or []
        new_words = []
        for w in aligned_words:
            text = (w.get("word") or w.get("text") or "").strip()
            start = w.get("start")
            end = w.get("end")
            # Sla woorden zonder geldige tijden over (WhisperX kan None geven)
            if not text or start is None or end is None:
                continue
            new_words.append({"start": float(start), "end": float(end), "text": text})
        if new_words:
            seg["words"] = new_words
    return whisper_segments


def forced_align(
    audio_path: str,
    whisper_segments: List[dict],
    language: str = "nl",
    device: str = "cpu",
    model_cache: Optional[Dict] = None,
) -> List[dict]:
    """Voer wav2vec2 forced alignment uit en geef whisper_segments terug met
    verfijnde woord-timestamps. Vereist whisperx + torch.

    Bij elke fout (geen lib, geen audio, modelprobleem) wordt het origineel
    onveranderd teruggegeven - de pipeline degradeert dan naar Faster-Whisper.
    """
    try:
        import whisperx

        # Segmenten in WhisperX-formaat
        wx_segments = [
            {"start": s["start"], "end": s["end"], "text": s.get("text", "")}
            for s in whisper_segments
        ]
        if not wx_segments:
            return whisper_segments

        cache = model_cache if model_cache is not None else {}
        key = (language, device)
        if key not in cache:
            model_a, metadata = whisperx.load_align_model(
                language_code=language, device=device
            )
            cache[key] = (model_a, metadata)
        model_a, metadata = cache[key]

        audio = whisperx.load_audio(audio_path)
        result = whisperx.align(
            wx_segments, model_a, metadata, audio, device,
            return_char_alignments=False,
        )
        aligned = result.get("segments", [])
        logger.info("Forced alignment voltooid", segments=len(aligned))
        return apply_aligned_words(whisper_segments, aligned)
    except Exception as e:  # pragma: no cover - vereist whisperx/torch
        logger.warning("Forced alignment overgeslagen", error=str(e))
        return whisper_segments
