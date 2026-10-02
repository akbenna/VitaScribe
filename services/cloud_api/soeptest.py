"""
VitaScribe Cloud API - SOEP-test: Claude tegen Mistral op dezelfde tekst

Voor de beheerder. Eén transcript (uit de vaste testset, of het laatste uit de
spraaktest) gaat door dezelfde SOEP-stap als een echt consult, één keer met
Claude (Anthropic) en één keer met het EU-model (Mistral). Zo is te zien of
de EU-modus even goede verslagen maakt.

Naast elk verslag staat wat verdacht is: dingen die in het verslag staan maar
niet in het gesprek. Dat is een eenvoudige, strenge controle, geen oordeel:
- een hoeveelheid met eenheid (500 mg, 10 ml) die niet in het gesprek staat;
- een bloeddruk (145/90) die niet in het gesprek staat;
- een plaatsaanduiding (lateraal, mediaal, ...) of zijde (links, rechts) die
  het gesprek niet noemt;
- "uitgesloten": in een verslag hoort "geen aanwijzingen voor".

Endpoints (beheerder):
  GET  /api/v1/beheer/testset      de consulten van de testset (zonder tekst)
  POST /api/v1/beheer/soeptest     json: id of gesprek, taal?
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import data_policy, pipeline, register
from .beheer import vereis_beheerder
from .medical_vocabulary import correct_transcript_full

logger = structlog.get_logger()
router = APIRouter(tags=["soeptest"])

TESTSET = Path(__file__).parent / "testset"
MAX_GESPREK = 100_000

# No \b before the number: "6dd500mg" must also be caught.
_EENHEID = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s?(mg|mcg|µg|microgram|gram|g|ml|ie|eh)\b", re.IGNORECASE)
_BLOEDDRUK = re.compile(r"\b(\d{2,3})\s?/\s?(\d{2,3})\b")
_PLAATS = ("lateraal", "laterale", "mediaal", "mediale", "dorsaal", "dorsale", "volair", "volaire",
           "plantair", "plantaire", "proximaal", "distaal")
_ZIJDE = {"links": ("links", "linker", "linkerkant", "li "), "rechts": ("rechts", "rechter", "rechterkant", "re ")}


def index() -> List[dict]:
    try:
        return json.loads((TESTSET / "index.json").read_text(encoding="utf-8"))["consulten"]
    except (OSError, ValueError, KeyError):
        return []


def gesprek_uit_testset(consult_id: str) -> str:
    if consult_id not in {c["id"] for c in index()}:
        raise HTTPException(status_code=404, detail="Onbekend consult in de testset.")
    return (TESTSET / f"{consult_id}.txt").read_text(encoding="utf-8")


def _soep_tekst(problemen: List[dict]) -> str:
    return "\n".join(str(p.get(k) or "") for p in problemen for k in ("s", "o", "e", "p"))


def verdacht(problemen: List[dict], gesprek: str) -> List[str]:
    """What the report says that the conversation does not (strict and simple)."""
    soep = _soep_tekst(problemen)
    laag = soep.lower()
    bron = " " + re.sub(r"\s+", " ", gesprek.lower()) + " "
    bron_kort = bron.replace(" ", "")
    uit: List[str] = []
    for m in _EENHEID.finditer(soep):
        getal, eenheid = m.group(1).replace(",", "."), m.group(2).lower()
        if f"{getal}{eenheid}" not in bron_kort and f"{getal} {eenheid}" not in bron:
            uit.append(f"hoeveelheid niet in het gesprek: {m.group(0)}")
    for m in _BLOEDDRUK.finditer(soep):
        if m.group(1) not in bron or m.group(2) not in bron:
            uit.append(f"waarde niet in het gesprek: {m.group(0)}")
    for woord in _PLAATS:
        if re.search(rf"\b{woord}\b", laag) and woord[:5] not in bron:
            uit.append(f"plaats niet in het gesprek: {woord}")
    for zijde, vormen in _ZIJDE.items():
        in_soep = any(re.search(rf"\b{v.strip()}\b", laag) for v in vormen)
        in_gesprek = any(v.strip() in bron for v in vormen[:3])
        if in_soep and not in_gesprek:
            uit.append(f"zijde niet in het gesprek: {zijde}")
    if re.search(r"\buitgesloten\b", laag):
        uit.append('"uitgesloten": in een verslag liever "geen aanwijzingen voor"')
    return list(dict.fromkeys(uit))


class SoepTestVraag(BaseModel):
    id: Optional[str] = None
    gesprek: str = Field("", max_length=MAX_GESPREK)
    taal: Optional[str] = "nl"


async def _een(gesprek: str, aanbieder: str, taal: Optional[str]) -> dict:
    start = time.monotonic()
    try:
        verbeterd, _ = correct_transcript_full(gesprek)
        soep = await pipeline.genereer_soep(verbeterd, aanbieder, taal)
    except Exception as exc:  # one failing model does not hide the other
        logger.warning("soeptest.fout", aanbieder=aanbieder, error=type(exc).__name__)
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {"aanbieder": aanbieder, "fout": detail[:300], "seconden": round(time.monotonic() - start, 1)}
    delen = soep.problemen or [{k: getattr(soep, k) for k in pipeline.SOEP_VELDEN}]
    return {"aanbieder": aanbieder, "seconden": round(time.monotonic() - start, 1),
            "problemen": delen, "verdacht": verdacht(delen, gesprek)}


@router.get("/api/v1/beheer/testset")
async def testset(door: str = Depends(vereis_beheerder)):
    return {"consulten": [{k: c.get(k) for k in ("id", "titel", "bron", "duur_seconden", "valkuilen")}
                          for c in index()]}


@router.post("/api/v1/beheer/soeptest")
async def soeptest(vraag: SoepTestVraag, door: str = Depends(vereis_beheerder)):
    """The same conversation to Claude and to the EU model, side by side."""
    gesprek = gesprek_uit_testset(vraag.id) if vraag.id else vraag.gesprek
    if not gesprek.strip():
        raise HTTPException(status_code=400, detail="Kies een consult uit de testset of maak eerst een vergelijking.")
    eu = data_policy.eu_llm_provider()
    claude, mistral = await asyncio.gather(_een(gesprek, "anthropic", vraag.taal), _een(gesprek, eu, vraag.taal))
    await register.log(door, "beheer.soeptest", consult=vraag.id or "eigen", claude_ok="problemen" in claude,
                       eu_ok="problemen" in mistral, verdacht_claude=len(claude.get("verdacht", [])),
                       verdacht_eu=len(mistral.get("verdacht", [])))
    valkuilen = next((c.get("valkuilen") for c in index() if c["id"] == vraag.id), []) if vraag.id else []
    return {"claude": claude, "eu": mistral, "eu_model": eu, "valkuilen": valkuilen}
