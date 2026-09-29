"""
VitaScribe Cloud API - Live consult

Volgt het gesprek tussen arts en patiënt terwijl het plaatsvindt, en maakt
na "stop" het verslag. Het geluid gaat in kleine stukjes via deze server
naar Deepgram (EU), dat de stemmen scheidt (diarize). De server bewaart
alleen de tekst per spreker, in het geheugen en alleen voor dit consult.
Na "stop" gaat dat transcript door dezelfde verwerking als een opgenomen
consult (pipeline.verwerk_transcript).

Waarom live en niet achteraf uploaden: het verslag staat er een paar
seconden na "stop" in plaats van na het uploaden en uitschrijven van het
hele consult, er is geen grens aan de bestandsgrootte, en er staat nooit
een audiobestand op de server. De extensie houdt zelf een kopie van de
opname tot het verslag binnen is; valt de verbinding weg, dan stuurt zij
die kopie alsnog op de gewone manier (/api/v1/consult/process).

Tijdens het consult krijgt de arts geen meelopende tekst te zien, alleen
dat er geluisterd wordt en hoeveel stemmen er zijn gehoord. Tussentijdse
tekst is vaak nog fout en leidt af van de patiënt.

Protocol (WebSocket /api/v1/consult/stream):
  client -> server  {"type": "auth", "api_key": "...", "praktijk": "...",
                     "consent": true, "keyterms": [...], "llm_provider": ...,
                     "vraagsuggesties": bool}
  client -> server  <binaire audio, webm/opus>
  client -> server  {"type": "nadictaat", "vanaf": 312.4}
                                                          de patiënt is weg; vanaf deze
                                                          seconde spreekt alleen de arts
  client -> server  {"type": "stop"}
  server -> client  {"type": "ready"}
  server -> client  {"type": "voortgang", "seconden": 12.3, "sprekers": 2}
  server -> client  {"type": "suggesties", "klacht": "...", "vragen": [{"tekst": "koorts?", "alarm": false}]}
                                                          alleen met CLINICAL_DECISION_SUPPORT en
                                                          "vraagsuggesties": true in auth
  server -> client  {"type": "verwerken"}
  server -> client  {"type": "result", "data": {...}, "leeg": bool}
  server -> client  {"type": "error", "message": "...", "terugval": bool}
  server -> client  {"type": "closed"}

"terugval": true betekent: stuur de eigen opname alsnog op.
Compatible with Python 3.9+.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from . import audit, pipeline, talen, vraagsuggesties
from .config import AppConfig, get_config
from .dictation import (
    KEYTERM_RETRY_BUDGETS,
    MAX_KEYTERM_TOKENS,
    _authenticate,
    _default_connect,
    _send_json,
    build_keyterms,
    sanitize_user_keyterms,
)
from .stt_service import NADICTAAT, TranscriptResult, TranscriptSegment

logger = structlog.get_logger()

UPSTREAM_CLOSE_TIMEOUT_SECS = 10.0


def max_seconden() -> int:
    """Kostenrem: een vergeten microfoon mag niet uren doorlopen."""
    try:
        return int(os.getenv("CONSULT_LIVE_MAX_SECONDS", "2700"))
    except ValueError:
        return 2700


def build_consult_url(cfg: AppConfig, user_terms: Optional[List[str]] = None,
                      token_budget: int = MAX_KEYTERM_TOKENS,
                      taal: Optional[talen.Taal] = None) -> str:
    """Streaming-adres voor een gesprek: stemmen scheiden, geen tussentekst.

    taal: de taal die de arts voor dit consult koos; zonder keuze de
    serverinstelling (Nederlands)."""
    model = cfg.stt.deepgram_model
    params: List[tuple] = [
        ("model", model),
        ("language", taal.deepgram if taal else cfg.stt.deepgram_language),
        ("punctuate", "true"),
        ("smart_format", "true"),
        ("diarize", "true"),
        ("interim_results", "false"),
        # AVG: niet bewaard en niet gebruikt voor training.
        ("mip_opt_out", "true"),
    ]
    if (token_budget > 0 and cfg.dictation.keyterms_enabled and model.startswith("nova-3")
            and (taal is None or taal.keyterms)):
        params.extend(("keyterm", term) for term in build_keyterms(user_terms, token_budget))
    return f"{cfg.dictation.deepgram_url}?{urlencode(params)}"


class Gesprek:
    """De tekst van het consult per spreker, opgebouwd uit Deepgram-finals."""

    def __init__(self) -> None:
        self.segmenten: List[TranscriptSegment] = []
        self.sprekers: set = set()
        self.seconden = 0.0
        self.nadictaat_vanaf: Optional[float] = None

    def start_nadictaat(self, vanaf: Any) -> None:
        """Vanaf deze seconde van de opname dicteert alleen de arts nog."""
        try:
            waarde = float(vanaf)
        except (TypeError, ValueError):
            return
        if waarde >= 0:
            self.nadictaat_vanaf = waarde

    def verwerk(self, raw: Any) -> bool:
        """Neemt een Deepgram-bericht op. True als er tekst bij kwam."""
        if isinstance(raw, bytes):
            return False
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return False
        if data.get("type") == "Metadata":
            self.seconden = max(self.seconden, float(data.get("duration") or 0.0))
            return False
        if data.get("type") != "Results" or not data.get("is_final"):
            return False
        alternatieven = (data.get("channel") or {}).get("alternatives") or [{}]
        woorden = alternatieven[0].get("words") or []
        erbij = False
        for w in woorden:
            tekst = (w.get("punctuated_word") or w.get("word") or "").strip()
            if not tekst:
                continue
            begin, eind = float(w.get("start") or 0.0), float(w.get("end") or 0.0)
            if self.nadictaat_vanaf is not None and (begin + eind) / 2 >= self.nadictaat_vanaf:
                spreker = NADICTAAT
            else:
                spreker = f"spreker_{w.get('speaker', 0)}"
            laatste = self.segmenten[-1] if self.segmenten else None
            if laatste is not None and laatste.speaker == spreker:
                laatste.text += " " + tekst
                laatste.end = eind
            else:
                self.segmenten.append(TranscriptSegment(text=tekst, start=begin, end=eind, speaker=spreker))
            if spreker != NADICTAAT:
                self.sprekers.add(spreker)
            self.seconden = max(self.seconden, eind)
            erbij = True
        return erbij

    def transcript(self) -> TranscriptResult:
        return TranscriptResult(
            raw_text=" ".join(s.text for s in self.segmenten),
            segments=list(self.segmenten),
            language="nl",
            duration_secs=round(self.seconden, 1),
            provider="deepgram-live",
        )


async def volg_consult(
    ws: WebSocket,
    connect: Callable[[str, str], Any] = _default_connect,
    verwerk: Callable[..., Any] = pipeline.verwerk_transcript,
) -> None:
    """Een live consult: audio in, na stop het verslag uit."""
    await ws.accept()
    cfg = get_config()

    auth, ident = await _authenticate(ws)
    if auth is None:
        await _send_json(ws, {"type": "error", "message": ident, "terugval": False})
        await ws.close(code=4401)
        return

    # KNMG (2026): een consult opnemen mag alleen met toestemming van de patiënt.
    if os.getenv("REQUIRE_RECORDING_CONSENT", "true").lower() == "true" and auth.get("consent") is not True:
        audit.log_event(ident.label, "consult.refused", status="geen_toestemming")
        await _send_json(ws, {"type": "error", "terugval": False,
                              "message": "Toestemming van de patiënt voor de opname is niet bevestigd."})
        await ws.close(code=4400)
        return

    from fastapi import HTTPException
    from .praktijk_sleutels import kies_spraak
    try:
        deepgram_key = await kies_spraak(ident)
    except HTTPException as exc:
        await _send_json(ws, {"type": "error", "message": exc.detail, "terugval": False})
        await ws.close(code=4403)
        return
    if not deepgram_key:
        await _send_json(ws, {"type": "error", "terugval": True,
                              "message": "Spraakherkenning is niet ingesteld op de server."})
        await ws.close(code=4500)
        return

    user_terms = sanitize_user_keyterms(auth.get("keyterms"))
    taal = talen.kies(auth.get("taal"))
    upstream = None
    last_exc: Optional[Exception] = None
    for budget in KEYTERM_RETRY_BUDGETS:
        try:
            upstream = await connect(build_consult_url(cfg, user_terms, budget, taal), deepgram_key)
            break
        except Exception as exc:
            last_exc = exc
            logger.warning("consult_live.upstream_connect_failed", error=str(exc), keyterm_budget=budget)
            if "400" not in str(exc):
                break
    if upstream is None:
        await _send_json(ws, {"type": "error", "terugval": True,
                              "message": f"Kan spraakherkenning niet bereiken: {last_exc}"})
        await ws.close(code=4502)
        return

    audit.log_event(ident.label, "consult.stream", consent=True)
    logger.info("consult_live.start", model=cfg.stt.deepgram_model, taal=taal.code)
    await _send_json(ws, {"type": "ready"})

    gesprek = Gesprek()
    gestopt = asyncio.Event()   # de arts klikte op stop (of de tijd is om)
    # Vraagsuggesties: alleen als server en arts het allebei aanzetten.
    meedenker = (vraagsuggesties.Meedenker(lambda payload: _send_json(ws, payload), ident.label,
                                           auth.get("llm_provider"))
                 if vraagsuggesties.toegestaan(auth) else None)

    async def client_naar_deepgram() -> None:
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes"):
                    await upstream.send(message["bytes"])
                elif message.get("text"):
                    try:
                        control = json.loads(message["text"])
                    except ValueError:
                        continue
                    if control.get("type") == "nadictaat":
                        gesprek.start_nadictaat(control.get("vanaf"))
                    elif control.get("type") == "stop":
                        gestopt.set()
                        break
        except WebSocketDisconnect:
            return
        try:
            await upstream.send(json.dumps({"type": "CloseStream"}))
        except Exception:
            pass

    async def deepgram_naar_gesprek() -> None:
        try:
            async for raw in upstream:
                if gesprek.verwerk(raw):
                    await _send_json(ws, {"type": "voortgang", "seconden": round(gesprek.seconden, 1),
                                          "sprekers": len(gesprek.sprekers)})
                    if meedenker is not None and not gestopt.is_set():
                        meedenker.misschien(gesprek)
        except Exception as exc:
            logger.warning("consult_live.upstream_closed", error=str(exc))

    zender = asyncio.create_task(client_naar_deepgram())
    ontvanger = asyncio.create_task(deepgram_naar_gesprek())
    start = time.time()
    try:
        klaar, _ = await asyncio.wait({zender, ontvanger}, timeout=max_seconden(),
                                      return_when=asyncio.FIRST_COMPLETED)
        if not klaar:
            # Tijd om: stoppen en verwerken wat er is.
            zender.cancel()
            gestopt.set()
            try:
                await upstream.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
        elif ontvanger in klaar and not gestopt.is_set():
            # Deepgram viel weg terwijl het consult nog liep.
            zender.cancel()
            await _send_json(ws, {"type": "error", "terugval": True,
                                  "message": "De live verbinding met de spraakherkenning viel weg."})
            return

        if not gestopt.is_set():
            return   # de extensie verbrak de verbinding zonder stop: niets te doen

        try:
            await asyncio.wait_for(ontvanger, timeout=UPSTREAM_CLOSE_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            ontvanger.cancel()

        await _send_json(ws, {"type": "verwerken"})
        transcript = gesprek.transcript()
        result = await verwerk(transcript, llm_provider=auth.get("llm_provider"), taal=taal.code)
        data = result.to_dict()
        data["processing_time_secs"] = round(time.time() - start, 2)
        await _send_json(ws, {"type": "result", "data": data, "leeg": not transcript.raw_text.strip()})
        logger.info("consult_live.complete", seconden=transcript.duration_secs,
                    sprekers=len(gesprek.sprekers))
    except Exception as exc:
        logger.error("consult_live.error", error=str(exc))
        await _send_json(ws, {"type": "error", "terugval": True,
                              "message": "Het verslag kon niet worden gemaakt."})
    finally:
        if meedenker is not None:
            meedenker.stop()
        for taak in (zender, ontvanger):
            if not taak.done():
                taak.cancel()
        try:
            await upstream.close()
        except Exception:
            pass
        await _send_json(ws, {"type": "closed"})
        try:
            await ws.close()
        except RuntimeError:
            pass
