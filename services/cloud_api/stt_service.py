"""
VitaScribe Cloud API - Speech-to-Text Service

Pluggable STT with support for:
  - Groq Whisper (free tier, fast)
  - Deepgram Nova-3 (best Dutch accuracy, default)
  - OpenAI Whisper API
  - Mistral Voxtral Mini Transcribe (France, EU), with speaker labels

All providers return a unified TranscriptResult.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import os
import re

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import httpx
import structlog

from .config import get_config

logger = structlog.get_logger()


@dataclass
class TranscriptSegment:
    """A single segment of transcribed speech."""
    text: str
    start: float
    end: float
    speaker: str = ""
    confidence: float = 0.0


@dataclass
class TranscriptResult:
    """Unified transcription result across all providers."""
    raw_text: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    language: str = "nl"
    duration_secs: float = 0.0
    provider: str = ""


NADICTAAT = "nadictaat"


def markeer_nadictaat(transcript: TranscriptResult, vanaf: Optional[float]) -> TranscriptResult:
    """Alles vanaf 'vanaf' seconden is het nadictaat van de arts.

    De arts klikt op "Nadicteren" als de patiënt weg is en dicteert dan kort
    onderzoek en beleid. De extensie stuurt mee op welke seconde van de
    opname dat was. Een uiting telt als nadictaat als haar midden na dat
    moment ligt; een zin die net over de grens loopt, valt zo aan de kant
    waar het meeste ervan staat.
    """
    if vanaf is None or vanaf < 0:
        return transcript
    for seg in transcript.segments or []:
        if (seg.start + seg.end) / 2 >= vanaf:
            seg.speaker = NADICTAAT
    return transcript


def met_sprekers(transcript: TranscriptResult) -> str:
    """Het transcript per spreker, zoals het taalmodel het moet lezen.

    Deepgram scheidt de stemmen (diarize) en geeft per uiting een spreker.
    Zonder die labels krijgt het model een lap tekst en moet het raden wie
    de klacht vertelt en wie onderzoekt; met de labels kan het klachten in S
    en bevindingen in O zetten. Opeenvolgende uitingen van dezelfde spreker
    worden een alinea. Er staat bewust "Spreker 1" en niet "arts": wie de
    arts is, leidt het model af uit wat er gezegd wordt, want de
    sprekerherkenning weet dat niet en kan zich vergissen.

    Het nadictaat is wel zeker van de arts: dat komt als laatste blok,
    "Nadictaat arts: ...".

    Is er maar een spreker en geen nadictaat, of geven de segmenten geen
    spreker (Groq, OpenAI), dan blijft het de gewone tekst.
    """
    segmenten = getattr(transcript, "segments", None)
    if not isinstance(segmenten, list):
        return transcript.raw_text
    met_tekst = [s for s in segmenten if (s.text or "").strip()]
    nadictaat = [s.text.strip() for s in met_tekst if s.speaker == NADICTAAT]
    gesprek = [s for s in met_tekst if s.speaker != NADICTAAT]
    gelabeld = [s for s in gesprek if getattr(s, "speaker", "")]
    meerdere = len({s.speaker for s in gelabeld}) >= 2
    if not nadictaat and not meerdere:
        return transcript.raw_text

    regels: List[str] = []
    if meerdere:
        nummers: dict = {}
        alineas: List[List[str]] = []
        vorige = None
        for s in gelabeld:
            if s.speaker not in nummers:
                nummers[s.speaker] = len(nummers) + 1
            if s.speaker != vorige:
                alineas.append([f"Spreker {nummers[s.speaker]}:"])
                vorige = s.speaker
            alineas[-1].append(s.text.strip())
        regels = [" ".join(a) for a in alineas]
    elif gesprek:
        regels = [" ".join(s.text.strip() for s in gesprek)]
    if nadictaat:
        regels.append("Nadictaat arts: " + " ".join(nadictaat))
    return "\n".join(regels)


async def transcribe(audio_path: Path, provider: str = None,
                     deepgram_key: Optional[str] = None,
                     language: Optional[str] = None) -> TranscriptResult:
    """Transcribe audio file using the specified or default provider.

    deepgram_key: the practice's own Deepgram key, if it has one.
    language: Deepgram language for this consult (talen.py); default nl."""
    config = get_config()
    provider = provider or config.stt.default_provider

    logger.info("stt.start", provider=provider, file=str(audio_path))

    if provider == "groq":
        return await _transcribe_groq(audio_path)
    elif provider == "deepgram":
        return await _transcribe_deepgram(audio_path, deepgram_key, language)
    elif provider == "openai":
        return await _transcribe_openai(audio_path)
    elif provider == "voxtral":
        return await _transcribe_voxtral(audio_path, language)
    else:
        raise ValueError(f"Onbekende STT provider: {provider}")


async def _transcribe_groq(audio_path: Path) -> TranscriptResult:
    """Transcribe using Groq's free Whisper API."""
    config = get_config()
    api_key = config.stt.groq_api_key
    if not api_key:
        raise ValueError("GROQ_API_KEY niet geconfigureerd.")

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(audio_path, "rb") as f:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio_path.name, f, "audio/webm")},
                data={
                    "model": config.stt.groq_model,
                    "language": "nl",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
            )
        response.raise_for_status()
        data = response.json()

    segments = []
    for seg in data.get("segments", []):
        segments.append(TranscriptSegment(
            text=seg.get("text", "").strip(),
            start=seg.get("start", 0.0),
            end=seg.get("end", 0.0),
            confidence=seg.get("avg_logprob", 0.0),
        ))

    return TranscriptResult(
        raw_text=data.get("text", ""),
        segments=segments,
        language=data.get("language", "nl"),
        duration_secs=data.get("duration", 0.0),
        provider="groq",
    )


async def _transcribe_deepgram(audio_path: Path, api_key: Optional[str] = None,
                               language: Optional[str] = None) -> TranscriptResult:
    """Transcribe using Deepgram (best Dutch accuracy), with speaker diarization."""
    config = get_config()
    language = language or config.stt.deepgram_language
    api_key = api_key or config.stt.deepgram_api_key
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY niet geconfigureerd.")

    # Detect content type from extension
    ext = audio_path.suffix.lower()
    content_types = {
        ".webm": "audio/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
    }
    content_type = content_types.get(ext, "audio/webm")

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        logger.info(
            "deepgram.request",
            audio_size_bytes=len(audio_data),
            audio_size_kb=round(len(audio_data) / 1024, 1),
            content_type=content_type,
            file_ext=ext,
            model=config.stt.deepgram_model,
            language=language,
        )

        response = await client.post(
            # EU endpoint: processing stays in the EU.
            os.getenv("DEEPGRAM_URL", "https://api.eu.deepgram.com/v1/listen"),
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": content_type,
            },
            params={
                "model": config.stt.deepgram_model,
                "language": language,
                "punctuate": "true",
                "diarize": "true",
                "smart_format": "true",
                "utterances": "true",
                # AVG: not kept, not used for training.
                "mip_opt_out": "true",
            },
            content=audio_data,
        )

        logger.info("deepgram.response_status", status_code=response.status_code)

        if response.status_code != 200:
            logger.error("deepgram.error", status=response.status_code, body=response.text[:500])

        response.raise_for_status()
        data = response.json()

    # Log full Deepgram response for debugging
    metadata = data.get("metadata", {})
    logger.info(
        "deepgram.result",
        duration=metadata.get("duration", 0),
        channels_count=len(data.get("results", {}).get("channels", [])),
        model_info=metadata.get("model_info", {}),
        request_id=metadata.get("request_id", ""),
    )

    result = data.get("results", {})
    channels = result.get("channels", [{}])
    alternatives = channels[0].get("alternatives", [{}]) if channels else [{}]
    transcript_text = alternatives[0].get("transcript", "") if alternatives else ""

    logger.info(
        "deepgram.transcript",
        text_length=len(transcript_text),
        confidence=alternatives[0].get("confidence", 0) if alternatives else 0,
    )

    segments = []
    for utt in result.get("utterances", []):
        segments.append(TranscriptSegment(
            text=utt.get("transcript", "").strip(),
            start=utt.get("start", 0.0),
            end=utt.get("end", 0.0),
            speaker=f"spreker_{utt.get('speaker', 0)}",
            confidence=utt.get("confidence", 0.0),
        ))

    metadata = data.get("metadata", {})
    duration = metadata.get("duration", 0.0)

    return TranscriptResult(
        raw_text=transcript_text,
        segments=segments,
        language="nl",
        duration_secs=duration,
        provider="deepgram",
    )


async def _transcribe_openai(audio_path: Path) -> TranscriptResult:
    """Transcribe using OpenAI Whisper API."""
    config = get_config()
    api_key = config.stt.openai_api_key
    if not api_key:
        raise ValueError("OPENAI_API_KEY niet geconfigureerd.")

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(audio_path, "rb") as f:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio_path.name, f, "audio/webm")},
                data={
                    "model": config.stt.openai_model,
                    "language": "nl",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
            )
        response.raise_for_status()
        data = response.json()

    segments = []
    for seg in data.get("segments", []):
        segments.append(TranscriptSegment(
            text=seg.get("text", "").strip(),
            start=seg.get("start", 0.0),
            end=seg.get("end", 0.0),
            confidence=seg.get("avg_logprob", 0.0),
        ))

    return TranscriptResult(
        raw_text=data.get("text", ""),
        segments=segments,
        language=data.get("language", "nl"),
        duration_secs=data.get("duration", 0.0),
        provider="openai",
    )


# ── Mistral Voxtral (EU) ──

VOXTRAL_URL = "https://api.mistral.ai/v1/audio/transcriptions"
MAX_CONTEXT_BIAS = 100   # Mistral accepts up to 100 words or phrases


def voxtral_context_bias() -> List[str]:
    """Medication names and terms from the vocabulary, so Voxtral spells them
    the Dutch way (the same list Deepgram gets as keyterms in dictation)."""
    from .medical_vocabulary import MEDICATION_CORRECTIONS, MEDICAL_TERM_CORRECTIONS
    termen: List[str] = []
    for bron in (MEDICATION_CORRECTIONS, MEDICAL_TERM_CORRECTIONS):
        for term in sorted(set(bron.values())):
            # Mistral refuses items with whitespace or commas ("vitamine D").
            if term and term not in termen and len(term) <= 40 and not re.search(r"[\s,]", term):
                termen.append(term)
    return termen[:MAX_CONTEXT_BIAS]


def _voxtral_taal(language: Optional[str]) -> Optional[str]:
    """Deepgram language codes ("nl", "multi", "en-GB") to Voxtral's two
    letters; "multi" means: let Voxtral detect the language."""
    code = (language or "nl").split("-")[0].lower()
    return None if code in ("multi", "") else code


# Voxtral sometimes writes Dutch fillers in English ("Yeah", "Okay"); in a
# Dutch consult they go back to Dutch. Only whole words, nothing else.
_ENGELS_VULWOORD = re.compile(r"\b(yeah|yep|okay)\b", re.IGNORECASE)
_NL_VOOR = {"yeah": "ja", "yep": "ja", "okay": "oké"}


def nederlandse_vulwoorden(tekst: str) -> str:
    def vervang(m: "re.Match") -> str:
        nl = _NL_VOOR[m.group(1).lower()]
        return nl.capitalize() if m.group(1)[0].isupper() else nl
    return _ENGELS_VULWOORD.sub(vervang, tekst)


async def transcribe_bytes(audio: bytes, provider: str, language: Optional[str] = None,
                           naam: str = "consult.webm") -> TranscriptResult:
    """Transcribe a recording held in memory (live consult); never on disk."""
    if provider != "voxtral":
        raise ValueError(f"Alleen Voxtral verwerkt een opname uit het geheugen, niet {provider}.")
    logger.info("stt.start", provider=provider, bytes=len(audio))
    return await _transcribe_voxtral(audio, language, naam=naam)


async def _transcribe_voxtral(audio_path: Union[Path, bytes], language: Optional[str] = None,
                              naam: str = "consult.webm", diarize: bool = True) -> TranscriptResult:
    """Transcribe using Mistral Voxtral Mini Transcribe, with speaker labels.

    Batch only: the recording is sent after the consult. Mistral keeps no
    audio for training on the API (verify the DPA before patient use).

    diarize=False: one speaker (an interpreter turn), so no speaker labels;
    the Dutch medical vocabulary then only goes along for Dutch speech."""
    config = get_config()
    api_key = config.llm.mistral_api_key
    if not api_key:
        raise ValueError("MISTRAL_API_KEY niet geconfigureerd.")
    # A list value is sent as a repeated form field (context_bias=…&context_bias=…).
    data = {"model": config.stt.voxtral_model}
    if diarize:
        data.update({"diarize": "true", "timestamp_granularities": "segment"})
    if diarize or _voxtral_taal(language) == "nl":
        # Words this doctor taught VitaScribe first (leren.py), then the standard list.
        from . import leren
        geleerd = [w for w in await leren.woordenlijst() if w and not re.search(r"[\s,]", w) and len(w) <= 40]
        data["context_bias"] = list(dict.fromkeys(geleerd + voxtral_context_bias()))[:MAX_CONTEXT_BIAS]
    taal = _voxtral_taal(language)
    if taal:
        data["language"] = taal

    async def post(velden: dict) -> httpx.Response:
        async with httpx.AsyncClient(timeout=300.0) as client:
            if isinstance(audio_path, (bytes, bytearray)):
                bestand = (naam, bytes(audio_path), "application/octet-stream")
                return await client.post(os.getenv("VOXTRAL_URL", VOXTRAL_URL),
                                         headers={"Authorization": f"Bearer {api_key}"},
                                         files={"file": bestand}, data=velden)
            with open(audio_path, "rb") as f:
                return await client.post(
                    os.getenv("VOXTRAL_URL", VOXTRAL_URL),
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, f, "application/octet-stream")},
                    data=velden,
                )

    response = await post(data)
    if response.status_code == 400 and "language" in data and "language" in response.text.lower():
        # Some options cannot be combined with a fixed language; let Voxtral detect it.
        logger.warning("voxtral.retry_without_language", body=response.text[:300])
        data.pop("language")
        response = await post(data)
    if response.status_code != 200:
        logger.error("voxtral.error", status=response.status_code, body=response.text[:500])
        try:
            melding = str(response.json().get("message") or "")[:200]
        except ValueError:
            melding = ""
        raise ValueError(f"Voxtral gaf fout {response.status_code}" + (f": {melding}" if melding else "."))
    body = response.json()

    nederlands = (taal or body.get("language") or "") == "nl"
    netjes = nederlandse_vulwoorden if nederlands else (lambda t: t)
    segments = []
    for seg in body.get("segments") or []:
        tekst = netjes((seg.get("text") or "").strip())
        if not tekst:
            continue
        spreker = seg.get("speaker_id")
        segments.append(TranscriptSegment(
            text=tekst,
            start=float(seg.get("start") or 0.0),
            end=float(seg.get("end") or 0.0),
            speaker=f"spreker_{spreker}" if spreker not in (None, "") else "",
            confidence=float(seg.get("score") or 0.0),
        ))
    usage = body.get("usage") or {}
    duur = float(usage.get("prompt_audio_seconds") or (segments[-1].end if segments else 0.0))
    tekst = netjes((body.get("text") or "").strip()) or " ".join(s.text for s in segments)
    logger.info("voxtral.result", chars=len(tekst), segments=len(segments),
                sprekers=len({s.speaker for s in segments if s.speaker}), duration=duur)
    return TranscriptResult(raw_text=tekst, segments=segments, language=body.get("language") or taal or "nl",
                            duration_secs=duur, provider="voxtral")
