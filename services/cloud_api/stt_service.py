"""
VitaScribe Cloud API - Speech-to-Text Service

Pluggable STT with support for:
  - Groq Whisper (free tier, fast)
  - Deepgram Nova-3 (best Dutch accuracy, default)
  - OpenAI Whisper API
  - Mistral Voxtral Mini Transcribe (France, EU), with speaker labels
  - Gladia (France, EU) and Speechmatics (UK, EU endpoint): batch, speaker
    labels, all languages of the interpreter (werkplan stap 6)

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
    elif provider == "gladia":
        return await _transcribe_gladia(audio_path, language)
    elif provider == "speechmatics":
        return await _transcribe_speechmatics(audio_path, language)
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
    if provider not in BATCH_EU:
        raise ValueError(f"Alleen een Europese batchdienst verwerkt een opname uit het geheugen, niet {provider}.")
    logger.info("stt.start", provider=provider, bytes=len(audio))
    return await transcribe_eu(audio, language, naam=naam, provider=provider)


# Batch speech services that are EU companies or process in the EU; one of
# them does the speech in the eu mode (data_policy.eu_stt_provider).
BATCH_EU = ("voxtral", "gladia", "speechmatics")


async def transcribe_eu(audio: Union[Path, bytes], language: Optional[str] = None, naam: str = "consult.webm",
                        diarize: bool = True, provider: Optional[str] = None) -> TranscriptResult:
    """The eu mode's speech service (or the one named). language: a Deepgram
    code ("nl", "multi", "ar-SY"); None or "multi" lets the service detect it."""
    from . import data_policy
    provider = provider or data_policy.eu_stt_provider()
    if provider == "gladia":
        return await _transcribe_gladia(audio, language, naam=naam, diarize=diarize)
    if provider == "speechmatics":
        return await _transcribe_speechmatics(audio, language, naam=naam, diarize=diarize)
    return await _transcribe_voxtral(audio, language, naam=naam, diarize=diarize)


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


# ── Shared by the EU batch services ──

def _taal_code(language: Optional[str]) -> Optional[str]:
    """Two letters ("ar-SY" -> "ar"); None for "multi" or nothing (detect)."""
    return _voxtral_taal(language) if language else None


async def _woordenlijst(max_items: int = 1000) -> List[str]:
    """The doctor's learned words first, then the standard vocabulary: the same
    list Voxtral gets, so a comparison is fair."""
    from . import leren
    geleerd = [w for w in await leren.woordenlijst() if w and len(w) <= 40]
    return list(dict.fromkeys(geleerd + voxtral_context_bias()))[:max_items]


def _lees(audio: Union[Path, bytes], naam: str) -> "tuple[str, bytes]":
    if isinstance(audio, (bytes, bytearray)):
        return naam, bytes(audio)
    return audio.name, Path(audio).read_bytes()


async def _wacht(client: httpx.AsyncClient, url: str, headers: dict, klaar, fout, dienst: str,
                 max_seconden: float = 600.0) -> dict:
    """Poll a job until klaar(body) or fout(body); short intervals first."""
    import asyncio
    import time as _time
    start, pauze = _time.monotonic(), 0.5
    while True:
        r = await client.get(url, headers=headers)
        if r.status_code != 200:
            logger.error(f"{dienst}.poll_error", status=r.status_code, body=r.text[:300])
            raise ValueError(f"{dienst.capitalize()} gaf fout {r.status_code}.")
        body = r.json()
        if klaar(body):
            return body
        reden = fout(body)
        if reden:
            logger.error(f"{dienst}.job_error", reason=str(reden)[:300])
            raise ValueError(f"{dienst.capitalize()} kon de opname niet verwerken: {str(reden)[:200]}")
        if _time.monotonic() - start > max_seconden:
            raise ValueError(f"{dienst.capitalize()} deed er te lang over.")
        await asyncio.sleep(pauze)
        pauze = min(pauze * 1.5, 3.0)


# ── Gladia (France, EU) ──

GLADIA_URL = "https://api.gladia.io"


async def _transcribe_gladia(audio: Union[Path, bytes], language: Optional[str] = None,
                             naam: str = "consult.webm", diarize: bool = True) -> TranscriptResult:
    """Upload, start a pre-recorded job, poll, read, and delete the job at
    Gladia, so nothing stays behind there."""
    api_key = get_config().stt.gladia_api_key
    if not api_key:
        raise ValueError("GLADIA_API_KEY niet geconfigureerd.")
    basis = os.getenv("GLADIA_URL", GLADIA_URL).rstrip("/")
    kop = {"x-gladia-key": api_key}
    taal = _taal_code(language)
    bestand, inhoud = _lees(audio, naam)
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{basis}/v2/upload", headers=kop,
                              files={"audio": (bestand, inhoud, "application/octet-stream")})
        if r.status_code not in (200, 201):
            logger.error("gladia.upload_error", status=r.status_code, body=r.text[:300])
            raise ValueError(f"Gladia gaf fout {r.status_code} bij het uploaden.")
        verzoek: dict = {
            "audio_url": r.json().get("audio_url"),
            "diarization": bool(diarize),
            "language_config": {"languages": [taal] if taal else [], "code_switching": not taal},
        }
        if diarize or taal == "nl":
            verzoek["custom_vocabulary"] = True
            verzoek["custom_vocabulary_config"] = {"vocabulary": await _woordenlijst(), "default_intensity": 0.5}
        r = await client.post(f"{basis}/v2/pre-recorded", headers=kop, json=verzoek)
        if r.status_code not in (200, 201):
            logger.error("gladia.error", status=r.status_code, body=r.text[:500])
            raise ValueError(f"Gladia gaf fout {r.status_code}.")
        job = r.json()
        job_url = job.get("result_url") or f"{basis}/v2/pre-recorded/{job.get('id')}"
        try:
            body = await _wacht(client, job_url, kop, lambda b: b.get("status") == "done",
                                lambda b: (b.get("error_code") or "fout") if b.get("status") == "error" else None,
                                "gladia")
        finally:
            if job.get("id"):
                await client.delete(f"{basis}/v2/pre-recorded/{job['id']}", headers=kop)
    resultaat = body.get("result") or {}
    transcriptie = resultaat.get("transcription") or {}
    talen = transcriptie.get("languages") or []
    gekozen = taal or (talen[0] if talen else "")
    netjes = nederlandse_vulwoorden if gekozen == "nl" else (lambda t: t)
    segments = []
    for u in transcriptie.get("utterances") or []:
        tekst = netjes((u.get("text") or "").strip())
        if not tekst:
            continue
        spreker = u.get("speaker")
        segments.append(TranscriptSegment(
            text=tekst, start=float(u.get("start") or 0.0), end=float(u.get("end") or 0.0),
            speaker=f"spreker_{spreker}" if diarize and spreker not in (None, "") else "",
            confidence=float(u.get("confidence") or 0.0)))
    duur = float((resultaat.get("metadata") or {}).get("audio_duration") or (segments[-1].end if segments else 0.0))
    tekst = netjes((transcriptie.get("full_transcript") or "").strip()) or " ".join(s.text for s in segments)
    logger.info("gladia.result", chars=len(tekst), segments=len(segments),
                sprekers=len({s.speaker for s in segments if s.speaker}), duration=duur)
    return TranscriptResult(raw_text=tekst, segments=segments, language=gekozen or "nl",
                            duration_secs=duur, provider="gladia")


# ── Speechmatics (UK, EU endpoint) ──

SPEECHMATICS_URL = "https://eu1.asr.api.speechmatics.com"


def _speechmatics_tekst(resultaten: List[dict]) -> List[TranscriptSegment]:
    """json-v2 words and punctuation to utterances per speaker."""
    segments: List[TranscriptSegment] = []
    for r in resultaten:
        alt = (r.get("alternatives") or [{}])[0]
        woord = str(alt.get("content") or "")
        if not woord:
            continue
        spreker = alt.get("speaker") or ""
        start, eind = float(r.get("start_time") or 0.0), float(r.get("end_time") or 0.0)
        if r.get("type") == "punctuation" or r.get("attaches_to") == "previous":
            if segments:
                segments[-1].text += woord
                segments[-1].end = max(segments[-1].end, eind)
            continue
        if segments and segments[-1].speaker == spreker and not segments[-1].text.endswith((".", "?", "!")):
            segments[-1].text += " " + woord
            segments[-1].end = eind
        else:
            segments.append(TranscriptSegment(text=woord, start=start, end=eind, speaker=spreker,
                                              confidence=float(alt.get("confidence") or 0.0)))
    return segments


async def _transcribe_speechmatics(audio: Union[Path, bytes], language: Optional[str] = None,
                                   naam: str = "consult.webm", diarize: bool = True) -> TranscriptResult:
    """Submit a batch job at the EU endpoint, poll, read json-v2, and delete
    the job, so nothing stays behind there."""
    import json as _json
    cfg = get_config().stt
    if not cfg.speechmatics_api_key:
        raise ValueError("SPEECHMATICS_API_KEY niet geconfigureerd.")
    basis = os.getenv("SPEECHMATICS_URL", SPEECHMATICS_URL).rstrip("/")
    kop = {"Authorization": f"Bearer {cfg.speechmatics_api_key}"}
    taal = _taal_code(language)
    instelling: dict = {"language": taal or "auto", "operating_point": cfg.speechmatics_operating_point}
    if diarize:
        instelling["diarization"] = "speaker"
    if diarize or taal == "nl":
        instelling["additional_vocab"] = [{"content": w} for w in await _woordenlijst()]
    config = {"type": "transcription", "transcription_config": instelling}
    if not taal:
        config["language_identification_config"] = {}
    bestand, inhoud = _lees(audio, naam)
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{basis}/v2/jobs", headers=kop,
                              files={"data_file": (bestand, inhoud, "application/octet-stream")},
                              data={"config": _json.dumps(config)})
        if r.status_code not in (200, 201):
            logger.error("speechmatics.error", status=r.status_code, body=r.text[:500])
            raise ValueError(f"Speechmatics gaf fout {r.status_code}.")
        job_id = r.json().get("id")
        if not job_id:
            raise ValueError("Speechmatics gaf geen opdrachtnummer terug.")
        try:
            await _wacht(client, f"{basis}/v2/jobs/{job_id}", kop,
                         lambda b: (b.get("job") or {}).get("status") == "done",
                         lambda b: (b.get("job") or {}).get("status") if (b.get("job") or {}).get("status")
                         in ("rejected", "deleted", "expired") else None, "speechmatics")
            r = await client.get(f"{basis}/v2/jobs/{job_id}/transcript", headers=kop, params={"format": "json-v2"})
            if r.status_code != 200:
                raise ValueError(f"Speechmatics gaf fout {r.status_code} bij het ophalen.")
            body = r.json()
        finally:
            if job_id:
                await client.delete(f"{basis}/v2/jobs/{job_id}", headers=kop, params={"force": "true"})
    gekozen = taal or str(((body.get("metadata") or {}).get("language_identification") or {}).get("most_likely_language")
                          or (body.get("metadata") or {}).get("transcription_config", {}).get("language") or "")
    if gekozen == "auto":
        gekozen = ""
    netjes = nederlandse_vulwoorden if gekozen == "nl" else (lambda t: t)
    segments = _speechmatics_tekst(body.get("results") or [])
    for s in segments:
        s.text = netjes(s.text)
        s.speaker = f"spreker_{s.speaker}" if diarize and s.speaker and s.speaker != "UU" else ""
    duur = float((body.get("job") or {}).get("duration") or (segments[-1].end if segments else 0.0))
    tekst = " ".join(s.text for s in segments)
    logger.info("speechmatics.result", chars=len(tekst), segments=len(segments),
                sprekers=len({s.speaker for s in segments if s.speaker}), duration=duur)
    return TranscriptResult(raw_text=tekst, segments=segments, language=gekozen or "nl",
                            duration_secs=duur, provider="speechmatics")
