"""
Transcription Service
=====================
Whisper Large v3 Turbo (Faster-Whisper) + PyAnnote diarisatie.
Verwerkt audio lokaal op GPU, output: getimed en gediariseerd transcript.
"""

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import structlog

# Maak shared/ importeerbaar (zelfde patroon als extraction/service.py)
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shared.vocabulary import (
    correct_transcript_full,
    get_hotwords,
    get_initial_prompt,
    load_custom_vocabulary,
)
from services.transcription.diarization_align import (
    SpeakerTurn,
    Word,
    aggregate_speaker_text,
    group_words_by_speaker,
)
from services.transcription.role_assignment import assign_roles

logger = structlog.get_logger()


@dataclass
class TranscriptSegment:
    """Enkel segment uit het transcript."""
    spreker: str           # "arts" of "patient"
    start: float           # Starttijd in seconden
    eind: float            # Eindtijd in seconden
    tekst: str
    confidence: float = 0.0


@dataclass
class TranscriptResult:
    """Volledig transcriptieresultaat."""
    segments: list[TranscriptSegment] = field(default_factory=list)
    raw_text: str = ""
    model_version: str = ""
    language: str = "nl"
    confidence_avg: float = 0.0
    duration_secs: float = 0.0
    word_count: int = 0
    corrections: int = 0      # Aantal toegepaste vocabulaire-naberekeningen

    def to_labeled_text(self) -> str:
        """Genereer gelabeld transcript voor LLM input."""
        lines = []
        for seg in self.segments:
            label = seg.spreker if seg.spreker in ("arts", "patient") else "onbekend"
            lines.append(f"{label}: {seg.tekst}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "segments": [
                {
                    "spreker": s.spreker,
                    "start": s.start,
                    "eind": s.eind,
                    "tekst": s.tekst,
                    "confidence": s.confidence,
                }
                for s in self.segments
            ],
            "model_version": self.model_version,
            "language": self.language,
            "confidence_avg": self.confidence_avg,
            "duration_secs": self.duration_secs,
            "word_count": self.word_count,
            "corrections": self.corrections,
        }


class TranscriptionService:
    """
    Lokale speech-to-text met Whisper + sprekerdiarisatie.

    Gebruik:
        service = TranscriptionService(config)
        await service.initialize()  # Laad modellen (eenmalig)
        result = await service.transcribe("/pad/naar/audio.wav")
    """

    def __init__(self, config):
        self.config = config
        self.whisper_model = None
        self.diarizer = None
        self._initialized = False
        self._initial_prompt = None   # Compacte medische context voor Whisper
        self._hotwords = None         # Volledige termenlijst voor hotwords-param
        self._align_cache = {}        # WhisperX alignment-modellen (per taal/device)

    async def initialize(self):
        """Laad Whisper en diarisatie modellen. Duurt ~30s bij eerste keer."""
        if self._initialized:
            return

        logger.info("Whisper model laden...",
                     model=self.config.whisper.model,
                     device=self.config.whisper.device)

        # --- Whisper laden ---
        try:
            from faster_whisper import WhisperModel

            device = self.config.whisper.device
            compute_type = self.config.whisper.compute_type

            # Automatische device detectie: CUDA > MPS (Apple Silicon) > CPU
            try:
                import torch
                if device == "cuda" and not torch.cuda.is_available():
                    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                        # Apple Silicon - faster-whisper ondersteunt geen MPS, gebruik CPU
                        device = "cpu"
                        compute_type = "int8"
                        logger.info("CUDA niet beschikbaar, Apple Silicon gedetecteerd - CPU mode met int8")
                    else:
                        device = "cpu"
                        compute_type = "int8"
                        logger.info("CUDA niet beschikbaar - CPU mode met int8")
            except ImportError:
                device = "cpu"
                compute_type = "int8"
                logger.info("PyTorch niet beschikbaar - CPU mode met int8")

            self.whisper_model = WhisperModel(
                self.config.whisper.model,
                device=device,
                compute_type=compute_type,
                download_root=self.config.whisper.model_path,
            )
            logger.info("Whisper model geladen", device=device, compute_type=compute_type)
        except Exception as e:
            logger.error("Whisper model laden mislukt", error=str(e))
            raise

        # --- Medische context-biasing voorbereiden ---
        # Laad eventueel geleerde (custom) correcties uit de feedbackloop, zodat
        # nieuwe termen meteen meegaan in hotwords/initial_prompt en naberekening.
        try:
            custom_path = Path(self.config.whisper.custom_vocab_path)
            n_custom = load_custom_vocabulary(custom_path)
            if n_custom:
                logger.info("Custom vocabulaire geladen", count=n_custom)
        except Exception as e:
            logger.warning("Custom vocabulaire laden mislukt", error=str(e))

        if self.config.whisper.use_initial_prompt:
            self._initial_prompt = get_initial_prompt()
        if self.config.whisper.use_hotwords:
            self._hotwords = get_hotwords()
        logger.info(
            "Medische context voorbereid",
            initial_prompt=bool(self._initial_prompt),
            hotwords=bool(self._hotwords),
        )

        # --- Diarisatie laden (optioneel) ---
        if self.config.diarization.enabled:
            try:
                from pyannote.audio import Pipeline

                self.diarizer = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.config.diarization.hf_token,
                )
                # Verplaats naar GPU indien beschikbaar
                import torch
                if torch.cuda.is_available():
                    self.diarizer.to(torch.device("cuda"))
                logger.info("Diarisatie pipeline geladen")
            except Exception as e:
                logger.warning("Diarisatie laden mislukt, gaat verder zonder",
                              error=str(e))
                self.diarizer = None

        self._initialized = True

    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """
        Transcribeer een audiobestand.

        Args:
            audio_path: Pad naar audiobestand (WAV/MP3/M4A/OGG/FLAC/WebM)

        Returns:
            TranscriptResult met segmenten, timestamps en confidence
        """
        if not self._initialized:
            await self.initialize()

        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audiobestand niet gevonden: {audio_path}")

        logger.info("Transcriptie gestart", audio_path=str(audio_path))

        # --- Stap 1: Whisper transcriptie ---
        # Medische context-biasing: initial_prompt (stijl + kerntermen) en
        # hotwords (volledige termenlijst) verlagen de woordfoutmarge op
        # medisch-Nederlandse termen. faster-whisper accepteert beide parameters.
        transcribe_kwargs = dict(
            language=self.config.whisper.language,
            beam_size=self.config.whisper.beam_size,
            word_timestamps=True,
            vad_filter=True,
        )
        if self._initial_prompt:
            transcribe_kwargs["initial_prompt"] = self._initial_prompt
        if self._hotwords:
            transcribe_kwargs["hotwords"] = self._hotwords

        segments_raw, info = self.whisper_model.transcribe(
            str(audio_path),
            **transcribe_kwargs,
        )

        # Verzamel segmenten
        whisper_segments = []
        all_text_parts = []
        total_confidence = 0.0

        for segment in segments_raw:
            # Woord-timestamps vastleggen (voor woord-niveau diarisatie)
            seg_words = []
            for w in (getattr(segment, "words", None) or []):
                seg_words.append({
                    "start": getattr(w, "start", segment.start),
                    "end": getattr(w, "end", segment.end),
                    "text": (getattr(w, "word", "") or "").strip(),
                })
            whisper_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "avg_logprob": segment.avg_logprob,
                "words": seg_words,
            })
            all_text_parts.append(segment.text.strip())
            total_confidence += segment.avg_logprob

        # --- Stap 1a2: Forced alignment (optioneel, WhisperX) ---
        # Verfijnt woord-timestamps via wav2vec2 zodat sprekergrenzen preciezer
        # op de woordgrens vallen. Valt terug op Faster-Whisper bij fout.
        if getattr(self.config.whisper, "use_forced_alignment", False):
            try:
                from services.transcription import whisperx_align
                whisper_segments = whisperx_align.forced_align(
                    str(audio_path),
                    whisper_segments,
                    language=info.language or self.config.whisper.language,
                    device=self.config.whisper.alignment_device,
                    model_cache=self._align_cache,
                )
            except Exception as e:
                logger.warning("Forced alignment overgeslagen", error=str(e))

        # --- Stap 1b: Deterministische naberekening via de woordenlijst ---
        # Corrigeert veelvoorkomende STT-fouten in medicatie-/medische termen
        # (bv. "metaformien" -> "metformine"). Transparant en auditeerbaar.
        corrections_total = 0
        if self.config.whisper.postcorrect_transcript:
            for seg in whisper_segments:
                corrected, stats = correct_transcript_full(seg["text"])
                seg["text"] = corrected
                corrections_total += stats.total_corrections
            all_text_parts = [s["text"] for s in whisper_segments]
            if corrections_total:
                logger.info("Transcript nabewerkt", corrections=corrections_total)

        raw_text = " ".join(all_text_parts)
        avg_confidence = (
            total_confidence / len(whisper_segments)
            if whisper_segments else 0.0
        )
        # Converteer log-prob naar 0-1 schaal (benadering)
        confidence_normalized = min(1.0, max(0.0, 1.0 + avg_confidence))

        logger.info("Whisper transcriptie voltooid",
                     segments=len(whisper_segments),
                     duration=info.duration,
                     confidence=round(confidence_normalized, 3))

        # --- Stap 2: Diarisatie (optioneel) ---
        if self.diarizer is not None:
            try:
                diarization = self.diarizer(str(audio_path))
                transcript_segments = self._merge_with_diarization(
                    whisper_segments, diarization
                )
            except Exception as e:
                logger.warning("Diarisatie mislukt, gebruik transcript zonder sprekerinfo",
                              error=str(e))
                transcript_segments = [
                    TranscriptSegment(
                        spreker="onbekend",
                        start=s["start"],
                        eind=s["end"],
                        tekst=s["text"],
                        confidence=min(1.0, max(0.0, 1.0 + s["avg_logprob"])),
                    )
                    for s in whisper_segments
                ]
        else:
            transcript_segments = [
                TranscriptSegment(
                    spreker="onbekend",
                    start=s["start"],
                    eind=s["end"],
                    tekst=s["text"],
                    confidence=min(1.0, max(0.0, 1.0 + s["avg_logprob"])),
                )
                for s in whisper_segments
            ]

        return TranscriptResult(
            segments=transcript_segments,
            raw_text=raw_text,
            model_version=self.config.whisper.model,
            language=info.language,
            confidence_avg=confidence_normalized,
            duration_secs=info.duration,
            word_count=len(raw_text.split()),
            corrections=corrections_total,
        )

    def _merge_with_diarization(
        self, whisper_segments: list[dict], diarization
    ) -> list[TranscriptSegment]:
        """
        Combineer Whisper-output met diarisatie op WOORD-niveau.

        Verbetering t.o.v. segment-niveau: één Whisper-segment kan twee sprekers
        overspannen (arts vraagt, patiënt antwoordt). Door elk woord aan de
        meest overlappende spreker toe te wijzen en daarna te hergroeperen,
        ontstaan zuivere sprekerbeurten. De arts/patiënt-rol wordt bepaald op
        taalkundige cues (zie role_assignment), niet op spreekvolgorde.

        Valt terug op segment-niveau als er geen woord-timestamps zijn.
        """
        turns = [
            SpeakerTurn(start=turn.start, end=turn.end, speaker=speaker)
            for turn, _, speaker in diarization.itertracks(yield_label=True)
        ]

        words = []
        for seg in whisper_segments:
            for w in (seg.get("words") or []):
                if w.get("text"):
                    words.append(Word(start=w["start"], end=w["end"], text=w["text"]))

        if not words or not turns:
            return self._merge_segment_level(whisper_segments, diarization)

        speaker_segments = group_words_by_speaker(words, turns)

        # Rollen bepalen uit de geaggregeerde tekst per spreker
        speaker_text = aggregate_speaker_text(speaker_segments)
        order = []
        for s in speaker_segments:
            if s.speaker not in order:
                order.append(s.speaker)
        roles = assign_roles(speaker_text, speaker_order=order)

        result = []
        for s in speaker_segments:
            tekst = s.text
            if self.config.whisper.postcorrect_transcript:
                tekst, _ = correct_transcript_full(tekst)
            result.append(TranscriptSegment(
                spreker=roles.get(s.speaker, "onbekend"),
                start=s.start,
                eind=s.end,
                tekst=tekst,
            ))
        return result

    def _merge_segment_level(
        self, whisper_segments: list[dict], diarization
    ) -> list[TranscriptSegment]:
        """Fallback: sprekertoewijzing op segment-niveau (zonder woord-timestamps).
        Rollen op taalkundige cues i.p.v. de oude 'eerste spreker = arts'."""
        turns = [
            SpeakerTurn(start=turn.start, end=turn.end, speaker=speaker)
            for turn, _, speaker in diarization.itertracks(yield_label=True)
        ]

        # Wijs elk segment toe aan de meest overlappende diarisatie-spreker
        per_segment_speaker = []
        for seg in whisper_segments:
            best_speaker = "onbekend"
            best_overlap = 0.0
            for t in turns:
                overlap = max(0.0, min(seg["end"], t.end) - max(seg["start"], t.start))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = t.speaker
            per_segment_speaker.append(best_speaker)

        # Geaggregeerde tekst per spreker -> rollen
        speaker_text: dict[str, list[str]] = {}
        order: list[str] = []
        for seg, spk in zip(whisper_segments, per_segment_speaker):
            speaker_text.setdefault(spk, []).append(seg["text"])
            if spk not in order:
                order.append(spk)
        roles = assign_roles(
            {k: " ".join(v) for k, v in speaker_text.items()},
            speaker_order=order,
        )

        result = []
        for seg, spk in zip(whisper_segments, per_segment_speaker):
            result.append(TranscriptSegment(
                spreker=roles.get(spk, "onbekend"),
                start=seg["start"],
                eind=seg["end"],
                tekst=seg["text"],
                confidence=min(1.0, max(0.0, 1.0 + seg["avg_logprob"])),
            ))
        return result
