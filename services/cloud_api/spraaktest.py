"""
VitaScribe Cloud API - Spraaktest: Voxtral (EU) tegen Deepgram

Een beheerder uploadt of neemt een opname op (bij voorkeur een rollenspel,
geen echte patiënt) en krijgt van beide spraakdiensten het transcript naast
elkaar, met wat er voor de keuze toe doet:

- verwerkingstijd en duur van de opname;
- het aantal sprekers en uitingen (arts en patiënt uit elkaar houden);
- hoeveel woorden, en hoe sterk de twee teksten overeenkomen;
- welke geneesmiddel- en vaktermen uit de woordenlijst elk herkende;
- de kosten per opname, en omgerekend per consult van tien minuten.

Er is geen "juiste" tekst om tegen te meten: de arts beoordeelt wie het beter
verstond. Er wordt niets bewaard; het auditlog noteert alleen dat er een test
was, met duur en uitkomst, zonder tekst.

Daarna kan de beheerder van beide transcripten een SOEP laten maken, met
precies de stappen van een echt consult (woordenlijst, dan het taalmodel voor
patiëntgegevens). Het verslag is wat in het dossier komt; daar moet het
verschil zichtbaar worden.

Endpoints (beheerder):
  POST /api/v1/beheer/spraaktest        multipart: audio, taal?, tegen? (voxtral | gladia |
                                        speechmatics; the EU service next to Deepgram, stap 6)
  POST /api/v1/beheer/spraaktest/soep   json: deepgram, voxtral, taal?
  GET  /beheer/spraaktest          de pagina
"""

from __future__ import annotations

import asyncio
import difflib
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import data_policy, leren, pipeline, register, stt_service
from .medical_vocabulary import correct_transcript_full
from .beheer import CSP, _pagina, vereis_beheerder

logger = structlog.get_logger()
router = APIRouter(tags=["spraaktest"])

MAX_BYTES = 60 * 1024 * 1024        # ruim een uur spraak in webm/opus
TOEGESTAAN = (".webm", ".wav", ".mp3", ".m4a", ".ogg", ".flac", ".mp4")
# Prijs per minuut in dollars: Deepgram Nova-3 (actie- tot lijstprijs) en
# Voxtral Mini Transcribe V2. Bron: zie de business case (oktober 2026).
MAX_TRANSCRIPT = 100_000           # tekens per transcript, ruim een uur gesprek
# The test page may embed the cookieless YouTube player (playlist test), and
# nothing else; no script from YouTube runs in this page. The embed needs the
# page's origin as referrer.
YOUTUBE = "https://www.youtube-nocookie.com"
CSP_SPRAAKTEST = CSP + f"; frame-src {YOUTUBE}"
PRIJS_PER_MINUUT = {"deepgram": (0.0048, 0.0077), "voxtral": (0.003, 0.003)}
# Gladia and Speechmatics: price per contract, not known here. Set
# PRIJS_<DIENST>_PER_MINUUT (dollars) to see it in the test; otherwise "offerte".
EU_NAAM = {"voxtral": "Voxtral (Mistral, Frankrijk)", "gladia": "Gladia (Frankrijk)",
           "speechmatics": "Speechmatics (VK, EU-endpoint)"}


def _prijs(naam: str):
    import os
    eigen = os.getenv(f"PRIJS_{naam.upper()}_PER_MINUUT", "").replace(",", ".").strip()
    try:
        return (float(eigen), float(eigen)) if eigen else PRIJS_PER_MINUUT.get(naam)
    except ValueError:
        return PRIJS_PER_MINUUT.get(naam)


def _woorden(tekst: str) -> list:
    return re.findall(r"[\wÀ-ÿ']+", (tekst or "").lower())


def overeenkomst(a: str, b: str) -> float:
    """Share of words the two transcripts have in common, in order (0-100)."""
    wa, wb = _woorden(a), _woorden(b)
    if not wa and not wb:
        return 100.0
    return round(100 * difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio(), 1)


def vaktermen(tekst: str) -> list:
    """Medication names and terms from the vocabulary that occur in the text."""
    from .medical_vocabulary import MEDICATION_CORRECTIONS, MEDICAL_TERM_CORRECTIONS
    laag = " " + " ".join(_woorden(tekst)) + " "
    gevonden = set()
    for term in set(MEDICATION_CORRECTIONS.values()) | set(MEDICAL_TERM_CORRECTIONS.values()):
        t = " ".join(_woorden(term))
        if t and f" {t} " in laag:
            gevonden.add(term)
    return sorted(gevonden, key=str.lower)


async def _een(naam: str, pad: Path, taal: str) -> dict:
    start = time.monotonic()
    try:
        res = await stt_service.transcribe(pad, provider=naam, language=taal)
    except Exception as exc:  # report per provider, never fail the whole test
        logger.warning("spraaktest.fout", provider=naam, error=type(exc).__name__)
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {"aanbieder": naam, "fout": detail[:300], "seconden": round(time.monotonic() - start, 1)}
    sec = round(time.monotonic() - start, 1)
    sprekers = {s.speaker for s in res.segments if s.speaker}
    minuten = (res.duration_secs or 0) / 60
    prijs = _prijs(naam)
    return {
        "aanbieder": naam,
        "seconden": sec,
        "duur_audio": round(res.duration_secs or 0, 1),
        "tekst": res.raw_text,
        "met_sprekers": stt_service.met_sprekers(res),
        "sprekers": len(sprekers),
        "uitingen": len(res.segments),
        "woorden": len(_woorden(res.raw_text)),
        "vaktermen": vaktermen(res.raw_text),
        "kosten_dollar": [round(minuten * prijs[0], 4), round(minuten * prijs[1], 4)] if prijs else None,
        "per_consult_10_min_dollar": [round(10 * prijs[0], 3), round(10 * prijs[1], 3)] if prijs else None,
    }


@router.get("/beheer/spraaktest", include_in_schema=False)
async def spraaktest_pagina():
    return _pagina("spraaktest.html", csp=CSP_SPRAAKTEST, referrer="strict-origin")


@router.get("/beheer/spraaktest.js", include_in_schema=False)
async def spraaktest_script():
    return _pagina("spraaktest.js")


@router.post("/api/v1/beheer/spraaktest")
async def spraaktest(audio: UploadFile = File(...), taal: Optional[str] = Form("nl"),
                     tegen: Optional[str] = Form("voxtral"), door: str = Depends(vereis_beheerder)):
    """Run the same recording through Deepgram and an EU service, side by side.
    The EU column keeps the key "voxtral" (the page and the SOEP step read it);
    "eu_dienst" and "eu_naam" say which service it was."""
    tegen = (tegen or "voxtral").strip().lower()
    if tegen not in stt_service.BATCH_EU:
        raise HTTPException(status_code=400, detail="Kies Voxtral, Gladia of Speechmatics.")
    if not data_policy.stt_sleutel(tegen):
        raise HTTPException(status_code=400, detail=f"Op de server is geen {data_policy.STT_SLEUTEL[tegen]} ingesteld.")
    naam = audio.filename or "opname.webm"
    ext = Path(naam).suffix.lower() or ".webm"
    if ext not in TOEGESTAAN:
        raise HTTPException(status_code=400, detail="Gebruik webm, wav, mp3, m4a, ogg, flac of mp4.")
    inhoud = await audio.read()
    if len(inhoud) < 1000:
        raise HTTPException(status_code=400, detail="De opname is leeg of te kort.")
    if len(inhoud) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="De opname is te groot (maximaal 60 MB).")
    taal = (taal or "nl").strip()[:8]

    with tempfile.TemporaryDirectory() as tmp:
        pad = Path(tmp) / f"spraaktest{ext}"
        pad.write_bytes(inhoud)
        deepgram, voxtral = await asyncio.gather(_een("deepgram", pad, taal), _een(tegen, pad, taal))

    beide = "tekst" in deepgram and "tekst" in voxtral
    uit = {
        "eu_dienst": tegen,
        "eu_naam": EU_NAAM[tegen],
        "deepgram": deepgram,
        "voxtral": voxtral,
        "overeenkomst": overeenkomst(deepgram["tekst"], voxtral["tekst"]) if beide else None,
        "alleen_deepgram": sorted(set(deepgram.get("vaktermen", [])) - set(voxtral.get("vaktermen", [])), key=str.lower),
        "alleen_voxtral": sorted(set(voxtral.get("vaktermen", [])) - set(deepgram.get("vaktermen", [])), key=str.lower),
    }
    # Content-free: who, how long, and how it went.
    await register.log(door, "beheer.spraaktest", bytes=len(inhoud),
                       duur=deepgram.get("duur_audio") or voxtral.get("duur_audio"),
                       deepgram_ok="tekst" in deepgram, eu_ok="tekst" in voxtral, eu_dienst=tegen,
                       overeenkomst=uit["overeenkomst"])
    return uit


class SoepVraag(BaseModel):
    deepgram: str = Field("", max_length=MAX_TRANSCRIPT)
    voxtral: str = Field("", max_length=MAX_TRANSCRIPT)
    taal: Optional[str] = "nl"


async def _soep(gesprek: str, aanbieder: str, taal: Optional[str]) -> dict:
    if not gesprek.strip():
        return {"fout": "Geen transcript."}
    start = time.monotonic()
    try:
        # The same steps as a real consult: vocabulary, then the PHI model.
        verbeterd, _ = correct_transcript_full(gesprek)
        leren.zet_eigenaar("")   # the speech test measures the system, not one doctor's style
        soep = await pipeline.genereer_soep(verbeterd, aanbieder, taal)
    except Exception as exc:  # one failing side does not hide the other
        logger.warning("spraaktest.soep_fout", error=type(exc).__name__)
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {"fout": detail[:300], "seconden": round(time.monotonic() - start, 1)}
    delen = soep.problemen or [{k: getattr(soep, k) for k in pipeline.SOEP_VELDEN}]
    return {"seconden": round(time.monotonic() - start, 1), "problemen": delen}


@router.post("/api/v1/beheer/spraaktest/soep")
async def spraaktest_soep(vraag: SoepVraag, door: str = Depends(vereis_beheerder)):
    """A SOEP from each transcript, side by side, with the production model."""
    if not (vraag.deepgram.strip() or vraag.voxtral.strip()):
        raise HTTPException(status_code=400, detail="Er is geen transcript om een SOEP van te maken.")
    aanbieder = data_policy.phi_llm_provider()
    deepgram, voxtral = await asyncio.gather(_soep(vraag.deepgram, aanbieder, vraag.taal),
                                             _soep(vraag.voxtral, aanbieder, vraag.taal))
    await register.log(door, "beheer.spraaktest_soep", taalmodel=aanbieder,
                       deepgram_ok="problemen" in deepgram, voxtral_ok="problemen" in voxtral)
    return {"taalmodel": aanbieder, "deepgram": deepgram, "voxtral": voxtral}
