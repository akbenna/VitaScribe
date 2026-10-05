"""
VitaScribe Cloud API - Live Dictation

Relays microphone audio from the side panel to Deepgram's streaming API and
sends transcript text back while the doctor is still speaking.

Client protocol (WebSocket /api/v1/dictation/stream):
  client -> server  {"type": "auth", "api_key": "...", "keyterms": [...]}
                                                          first message; keyterms
                                                          are optional user words
  client -> server  <binary audio chunks, webm/opus>
  client -> server  {"type": "stop"}                     flush and close
  server -> client  {"type": "ready"}
  server -> client  {"type": "transcript", "text": "...", "is_final": bool,
                     "speech_final": bool}
  server -> client  {"type": "suggesties", "klacht": "...", "vragen": [...]}
                    (only with "vraagsuggesties": true in auth and
                    CLINICAL_DECISION_SUPPORT on the server)
  server -> client  {"type": "error", "message": "..."}
  server -> client  {"type": "closed"}

The Deepgram key never leaves the server; audio is not stored.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from . import audit, data_policy
from . import licentie
from .config import AppConfig, get_config
from .medical_vocabulary import MEDICATION_CORRECTIONS, correct_transcript_full

logger = structlog.get_logger()

# Deepgram accepts at most 100 keyterms per request and at most 500 tokens
# across all keyterms; above that the handshake is refused (HTTP 400).
# Dutch medical words measure about 2.1 characters per token, so the
# estimate below (len/2 + 1) stays safely under the real count.
MAX_KEYTERMS = 100
MAX_KEYTERM_TOKENS = 450
KEYTERM_RETRY_BUDGETS = (MAX_KEYTERM_TOKENS, 200, 0)
MAX_USER_KEYTERMS = 50
MAX_KEYTERM_LENGTH = 50
AUTH_TIMEOUT_SECS = 10.0
UPSTREAM_CLOSE_TIMEOUT_SECS = 5.0

_SPOKEN_COMMANDS = [
    (re.compile(r"[\s,.]*\bnieuwe alinea\b[\s,.]*", re.IGNORECASE), "\n\n"),
    (re.compile(r"[\s,.]*\bnieuwe regel\b[\s,.]*", re.IGNORECASE), "\n"),
    # Spoken punctuation. "38 komma 5" is a number, not a comma.
    (re.compile(r"(\d)\s+komma\s+(\d)", re.IGNORECASE), r"\1,\2"),
    (re.compile(r"[\s,.]*\bdubbele punt\b[\s,.]*", re.IGNORECASE), ": "),
    (re.compile(r"[\s,.]*\bpuntkomma\b[\s,.]*", re.IGNORECASE), "; "),
    (re.compile(r"[\s,.]*\bvraagteken\b[\s,.]*", re.IGNORECASE), "? "),
    (re.compile(r"[\s,.]*\bkomma\b[\s,.]*", re.IGNORECASE), ", "),
    # "punt" only as the last word of a segment ("McBurney punt" stays).
    (re.compile(r"[\s,]*\bpunt\b[\s.]*$", re.IGNORECASE), ". "),
]


def sanitize_user_keyterms(raw: Any) -> List[str]:
    """Accept only short strings from the client, deduplicated, capped."""
    if not isinstance(raw, list):
        return []
    terms: List[str] = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        term = " ".join(item.split())
        if not term or len(term) > MAX_KEYTERM_LENGTH or term.lower() in seen:
            continue
        seen.add(term.lower())
        terms.append(term)
        if len(terms) >= MAX_USER_KEYTERMS:
            break
    return terms


# Words that general-practice dictation needs and a general speech model often
# mishears. Deepgram accepts at most 100 keyterms, so this list is curated:
# frequent GP diagnoses and exam terms, then the most prescribed drugs.
CORE_MEDICAL_TERMS: List[str] = [
    # diagnoses / klachten
    "hypertensie", "diabetes mellitus", "COPD", "astma", "atriumfibrilleren", "dyspnoe",
    "hartfalen", "angina pectoris", "pneumonie", "bronchitis", "sinusitis",
    "otitis media", "otitis externa", "tonsillitis", "faryngitis", "cystitis",
    "pyelonefritis", "urineweginfectie", "gastro-enteritis", "refluxziekte",
    "obstipatie", "prikkelbaredarmsyndroom", "lumbago", "lumbosacraal radiculair syndroom",
    "artrose", "jicht", "epicondylitis", "fasciitis plantaris", "tendinopathie",
    "migraine", "spanningshoofdpijn", "BPPV", "vertigo", "depressie",
    "angststoornis", "eczeem", "psoriasis", "impetigo", "erysipelas",
    "dermatomycose", "onychomycose", "urticaria", "conjunctivitis",
    "hypothyreoïdie", "anemie", "TIA", "CVA", "trombose", "longembolie",
    # onderzoek
    "auscultatie", "vesiculair ademgeruis", "crepitaties", "rhonchi", "souffle",
    "trommelvlies", "saturatie", "Lasègue", "Romberg", "Dix-Hallpike",
    "Barré", "McMurray", "Lachman", "hydrops", "defense", "peristaltiek",
]

CORE_MEDICATIONS: List[str] = [
    "paracetamol", "ibuprofen", "naproxen", "diclofenac", "amoxicilline",
    "amoxicilline-clavulaanzuur", "doxycycline", "nitrofurantoïne", "fosfomycine",
    "azitromycine", "claritromycine", "feneticilline", "flucloxacilline",
    "omeprazol", "pantoprazol", "metformine", "gliclazide", "atorvastatine",
    "simvastatine", "rosuvastatine", "amlodipine", "lisinopril", "enalapril",
    "losartan", "hydrochloorthiazide", "chloortalidon", "metoprolol",
    "bisoprolol", "furosemide", "apixaban", "rivaroxaban", "clopidogrel",
    "acetylsalicylzuur", "salbutamol", "fluticason", "budesonide", "tiotropium",
    "prednisolon", "sertraline", "citalopram", "oxazepam", "levothyroxine",
    "tramadol", "colecalciferol", "macrogol", "cetirizine",
]


def estimate_keyterm_tokens(term: str) -> int:
    """Conservative token estimate for Deepgram's keyterm budget."""
    return len(term) // 2 + 1


def build_keyterms(user_terms: Optional[List[str]] = None,
                   token_budget: int = MAX_KEYTERM_TOKENS) -> List[str]:
    """The doctor's own words first, then the curated medical terms and drugs,
    then the remaining vocabulary medication names; capped at Deepgram's
    limits on count and on total tokens."""
    terms: List[str] = []
    seen = set()
    budget = token_budget
    extra = sorted({name for name in MEDICATION_CORRECTIONS.values() if name})
    for term in list(user_terms or []) + CORE_MEDICAL_TERMS + CORE_MEDICATIONS + extra:
        if term.lower() in seen:
            continue
        cost = estimate_keyterm_tokens(term)
        if cost > budget:
            continue   # a shorter term further on may still fit
        terms.append(term)
        seen.add(term.lower())
        budget -= cost
        if len(terms) >= MAX_KEYTERMS:
            break
    return terms


def build_deepgram_url(cfg: AppConfig, user_terms: Optional[List[str]] = None,
                       token_budget: int = MAX_KEYTERM_TOKENS) -> str:
    """Streaming URL with low-latency settings for single-speaker dictation."""
    params: List[tuple] = [
        ("model", cfg.dictation.deepgram_model),
        ("language", cfg.dictation.deepgram_language),
        ("punctuate", "true"),
        ("smart_format", "true"),
        ("interim_results", "true"),
        ("endpointing", str(cfg.dictation.endpointing_ms)),
        # AVG: audio is not kept or used for training (Model Improvement Program off).
        ("mip_opt_out", "true"),
    ]
    # Keyterm prompting is a Nova-3 feature and billed as an add-on.
    if (token_budget > 0 and cfg.dictation.keyterms_enabled
            and cfg.dictation.deepgram_model.startswith("nova-3")):
        params.extend(("keyterm", term) for term in build_keyterms(user_terms, token_budget))
    return f"{cfg.dictation.deepgram_url}?{urlencode(params)}"


def apply_spoken_commands(text: str) -> str:
    """Turn spoken layout commands ("nieuwe regel") into line breaks."""
    for pattern, replacement in _SPOKEN_COMMANDS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"[ \t]+([,.;:?])", r"\1", text)      # no space before punctuation
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.rstrip(" ") if not text.endswith("\n") else text


def parse_deepgram_message(raw: str) -> Optional[Dict[str, Any]]:
    """Convert a Deepgram streaming message into a client transcript event.

    Returns None for messages the client doesn't need (metadata, empty results).
    Final segments get vocabulary correction and spoken-command handling;
    interim segments are passed through raw to keep latency minimal.
    """
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if data.get("type") != "Results":
        return None

    alternatives = data.get("channel", {}).get("alternatives") or [{}]
    text = (alternatives[0].get("transcript") or "").strip()
    if not text:
        return None

    is_final = bool(data.get("is_final"))
    if is_final:
        text, _stats = correct_transcript_full(text)
        text = apply_spoken_commands(text)

    return {
        "type": "transcript",
        "text": text,
        "is_final": is_final,
        "speech_final": bool(data.get("speech_final")),
    }


async def _default_connect(url: str, api_key: str):
    from websockets.asyncio.client import connect

    return await connect(
        url,
        additional_headers={"Authorization": f"Token {api_key}"},
        open_timeout=10,
        max_size=None,
    )


async def _authenticate(ws: WebSocket):
    """(auth message, identity) if the key and licence are valid; otherwise
    (None, message for the doctor). A browser cannot set headers on a
    WebSocket, so the practice numbers come in the auth message."""
    ongeldig = "Ongeldige of ontbrekende API-sleutel."
    try:
        first = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SECS)
        message = json.loads(first)
    except (asyncio.TimeoutError, ValueError, KeyError, WebSocketDisconnect):
        return None, ongeldig
    if not isinstance(message, dict) or message.get("type") != "auth":
        return None, ongeldig
    praktijk = message.get("praktijk")
    if isinstance(praktijk, list):
        praktijk = ",".join(str(p) for p in praktijk[:8])
    try:
        ident = await licentie.identificeer(str(message.get("api_key") or ""), praktijk if isinstance(praktijk, str) else None)
    except licentie.LicentieFout as fout:
        return None, fout.detail if fout.status == 403 and "Ongeldige" not in fout.detail else ongeldig
    # A browser cannot set headers on a WebSocket either: the mode comes here too.
    data_policy.zet_modus(message.get("modus"))
    return message, ident


async def _send_json(ws: WebSocket, payload: Dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
    except (RuntimeError, WebSocketDisconnect):
        pass


async def relay_dictation(
    ws: WebSocket,
    connect: Callable[[str, str], Any] = _default_connect,
) -> None:
    """Relay one dictation session between the client and Deepgram."""
    await ws.accept()
    cfg = get_config()

    auth, ident = await _authenticate(ws)
    if auth is None:
        await _send_json(ws, {"type": "error", "message": ident})
        await ws.close(code=4401)
        return

    if data_policy.eu_modus():
        # Live dictation needs Deepgram (US company); not in the formal EU mode.
        await _send_json(ws, {"type": "error", "message": "Live dicteren kan niet in de EU-modus. "
                              "Schakel bovenin naar de Claude-modus, of neem het consult op."})
        await ws.close(code=4403)
        return

    from fastapi import HTTPException
    from .praktijk_sleutels import kies_spraak
    try:
        deepgram_key = await kies_spraak(ident)
    except HTTPException as exc:
        await _send_json(ws, {"type": "error", "message": exc.detail})
        await ws.close(code=4403)
        return

    if not deepgram_key:
        await _send_json(ws, {"type": "error", "message": "DEEPGRAM_API_KEY niet geconfigureerd op de server."})
        await ws.close(code=4500)
        return

    from . import leren
    user_terms = sanitize_user_keyterms(leren.met_woorden(await leren.woordenlijst(), auth.get("keyterms")))
    upstream = None
    last_exc: Optional[Exception] = None
    # Deepgram counts keyterm tokens with its own tokenizer; codes and unusual
    # words cost more than our estimate. If the handshake is refused, retry
    # with a smaller keyterm set and finally without, so dictation still starts.
    for budget in KEYTERM_RETRY_BUDGETS:
        try:
            upstream = await connect(build_deepgram_url(cfg, user_terms, budget), deepgram_key)
            break
        except Exception as exc:  # handshake rejected, network, bad model/language
            last_exc = exc
            logger.warning("dictation.upstream_connect_failed", error=str(exc), keyterm_budget=budget)
            if "400" not in str(exc):
                break   # network or auth trouble: fewer keyterms won't help
    if upstream is None:
        await _send_json(ws, {"type": "error", "message": f"Kan spraakherkenning niet bereiken: {last_exc}"})
        await ws.close(code=4502)
        return

    logger.info("dictation.start", model=cfg.dictation.deepgram_model)
    audit.log_event(ident.label, "dictation.stream")
    await _send_json(ws, {"type": "ready"})

    # Question suggestions while dictating (clinical support): only when the
    # server allows it and the doctor switched it on (auth "vraagsuggesties").
    from . import vraagsuggesties
    meedenker = (vraagsuggesties.Meedenker(lambda payload: _send_json(ws, payload), ident.label,
                                           bron="dictaat")
                 if vraagsuggesties.toegestaan(auth) else None)
    finals: list = []

    async def client_to_upstream() -> None:
        # Ends on "stop", client disconnect or the session time limit.
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes"):
                    await upstream.send(message["bytes"])
                elif message.get("text"):
                    try:
                        control = json.loads(message["text"])
                    except ValueError:
                        continue
                    if control.get("type") == "stop":
                        break
        except WebSocketDisconnect:
            pass
        # Ask Deepgram to flush remaining finals, then close.
        try:
            await upstream.send(json.dumps({"type": "CloseStream"}))
        except Exception:
            pass

    async def upstream_to_client() -> None:
        try:
            async for raw in upstream:
                if isinstance(raw, bytes):
                    continue
                event = parse_deepgram_message(raw)
                if event:
                    await _send_json(ws, event)
                    if meedenker is not None and event.get("is_final") and event.get("text"):
                        finals.append(event["text"])
                        meedenker.misschien_tekst(" ".join(finals))
        except Exception as exc:
            logger.warning("dictation.upstream_closed", error=str(exc))

    sender = asyncio.create_task(client_to_upstream())
    receiver = asyncio.create_task(upstream_to_client())
    try:
        try:
            await asyncio.wait_for(asyncio.shield(sender), timeout=cfg.dictation.max_seconds)
        except asyncio.TimeoutError:
            # Cost guard: a forgotten open microphone must not stream for hours.
            await _send_json(ws, {"type": "error", "message": "Maximale dicteerduur bereikt; opname gestopt."})
            sender.cancel()
            try:
                await upstream.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
        try:
            await asyncio.wait_for(receiver, timeout=UPSTREAM_CLOSE_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            receiver.cancel()
    finally:
        if meedenker is not None:
            meedenker.stop()
        try:
            await upstream.close()
        except Exception:
            pass
        await _send_json(ws, {"type": "closed"})
        try:
            await ws.close()
        except RuntimeError:
            pass
        logger.info("dictation.end")
