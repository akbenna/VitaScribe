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
  POST /api/v1/beheer/soeptest     json: id of gesprek, taal?, run?
  POST /api/v1/beheer/testset/inzending  json: titel, bron, gesprek

Testset-runs (alleen de vaste, gespeelde consulten) komen met de volledige
verslagen in het serverlog ("soeptest.rapport"), zodat de ontwikkelaar ze
daar kan nalezen zonder kopiëren en plakken. Een inzending (een gespeeld
consult uit de spraaktest) gaat in stukken naar het log ("testset.inzending")
en wordt daarna met de hand aan de testset toegevoegd. Eigen gesprekken uit
een sessie gaan nooit met tekst in het log.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import data_policy, icpc_controle, leren, pipeline, register
from .beheer import vereis_beheerder
from .config import get_config
from .medical_vocabulary import correct_transcript_full

logger = structlog.get_logger()
router = APIRouter(tags=["soeptest"])

TESTSET = Path(__file__).parent / "testset"
MAX_GESPREK = 100_000

# No \b before the number: "6dd500mg" must also be caught.
# No \b before the number: "6dd500mg" must also be caught.
_EENHEID = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s?(mg|mcg|µg|microgram|gram|g|ml|ie|eh)\b", re.IGNORECASE)
_BLOEDDRUK = re.compile(r"\b(\d{2,3})\s?/\s?(\d{2,3})\b")
_PLAATS = ("lateraal", "laterale", "lateralis", "mediaal", "mediale", "medialis", "dorsaal", "dorsale",
           "volair", "volaire", "plantair", "plantaire", "proximaal", "distaal")
# Topics a report may only mention (also as a denial: "geen suïcidegedachten") if they were discussed.
_ONDERWERPEN = (
    ("suïcidaliteit", r"suïcid|suicid|doodswens|zelfmoord", r"suïcid|suicid|zelfmoord|dood (willen|wil)|doodswens|leven (niet meer|beëindigen)"),
    ("alcohol", r"\balcohol|\bbier\b|\bwijn\b", r"alcohol|\bbier|\bwijn|borrel|drank"),
    ("drugs", r"\bdrugs|cannabis|blowen|cocaïne|cocaine", r"drugs|cannabis|blow|cocaïne|cocaine|wiet"),
    ("roken", r"\broken\b|\brookt\b|sigaret|nicotine|packyears", r"\brook|roken|sigaret|nicotine"),
    ("koorts", r"\bkoorts|temperatuur|\btemp\b", r"koorts|temperatuur|verhoging"),
    ("gewichtsverlies", r"gewichtsverlies|gewichtsafname|afgevallen|kilo.{0,10}(kwijt|afgevallen)", r"afgevallen|gewicht|kilo"),
    ("nachtzweten", r"nachtzweten", r"nachtzweten|'s nachts (zweten|zweet)|nachts.{0,15}zwe"),
    ("allergie", r"allergie|allergisch", r"allergi"),
    ("cauda-equinasyndroom", r"cauda|mictiestoorn|defecatiestoorn|zadelanesthesie|mictie/defecatie",
     r"cauda|plassen|mictie|ontlasting|zadel"),
)
_AFGEBROKEN = re.compile(r"\(\s*[,;]|[,;]\s*\)|:\s+(en|maar)\s|(?<!\.)\.\.(?!\.)|\b(met|en|of|bij|naar|zonder)\s*[;](?!\w)|\b(en|of|zonder)\s*\.(?!\w)",
                         re.IGNORECASE)
# A strength score ("kracht 5/5") and the name of a physical test are typical
# of an exam filled in from a template rather than heard.
_KRACHT = re.compile(r"\b[0-5]\s?/\s?5\b")
_TESTNAMEN = ("lasègue", "lasegue", "lachman", "schuiflade", "mcmurray", "thessaly", "apley", "phalen", "tinel",
              "finkelstein", "hawkins", "neer", "jobe", "murphy", "kernig", "brudzinski", "romberg", "babinski",
              "fabere", "patrick", "homans", "trendelenburg")
_ZIJDE = {"links": ("links", "linker", "linkerkant", "li "), "rechts": ("rechts", "rechter", "rechterkant", "re ")}
# Vertebral levels ("L4-L5", "ter hoogte van L5") and landmarks nobody may add.
_WERVEL = re.compile(r"\b(?:L[1-5]|S1|C[1-7]|Th?1[0-2]|Th?[1-9])\s?[-–/]\s?(?:L[1-5]|S1|C[1-7]|Th?1[0-2]|Th?[1-9])\b"
                     r"|\b(?:hoogte|niveau)\s+(?:van\s+)?(?:L[1-5]|S1|C[1-7]|Th?1[0-2]|Th?[1-9])\b")
_ORIENTATIE = ("psis", "sips", "si-gewricht", "crista iliaca", "trochanter", "malleolus", "processus spinosus",
               "costovertebraal")
_FREQUENTIE = re.compile(r"\b(\d)\s?dd\s?(\d+)?", re.IGNORECASE)
_GETAL_WOORD = {"1": ("een", "één"), "2": ("twee",), "3": ("drie",), "4": ("vier",), "5": ("vijf",),
                "6": ("zes",), "8": ("acht",)}
_VANGNET_SOEP = re.compile(r"terug\s?k(om|wam)|terugkomen|controle|bij (geen|onvoldoende|uitblijven(de)?) "
                           r"(van )?verbetering|vangnet|opnieuw contact|weer contact", re.IGNORECASE)
_VANGNET_GESPREK = re.compile(r"terugkom|terugzien|kom(t|en)? (dan |je |u )?(gewoon |nog )?terug|controle|"
                              r"weer (komen|langs)|nog een keer (komen|langs)|afspraak|bel(t|len)? (dan|gewoon)|"
                              r"mag ik dan .{0,20}komen", re.IGNORECASE)


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


def _getal_in(getal: str, bron: str) -> bool:
    if re.search(rf"(?<!\d){getal}(?!\d)", bron):
        return True
    return any(re.search(rf"\b{w}\b", bron) for w in _GETAL_WOORD.get(getal, ()))


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
    for m in _FREQUENTIE.finditer(soep):
        if not all(_getal_in(g, bron) for g in m.groups() if g):
            uit.append(f"frequentie of aantal niet in het gesprek: {m.group(0).strip()}")
    for m in _WERVEL.finditer(soep):
        if m.group(0).lower() not in bron:
            uit.append(f"wervelniveau niet in het gesprek: {m.group(0)}")
    for woord in _ORIENTATIE:
        if woord in laag and woord not in bron:
            uit.append(f"anatomisch punt niet in het gesprek: {woord.upper() if len(woord) <= 4 else woord}")
    for woord in _PLAATS:
        if re.search(rf"\b{woord}\b", laag) and woord[:5] not in bron:
            uit.append(f"plaats niet in het gesprek: {woord}")
    for m in _KRACHT.finditer(soep):
        if m.group(0).replace(" ", "") not in bron_kort:
            uit.append(f"kracht of score niet in het gesprek: {m.group(0)}")
    for naam in _TESTNAMEN:
        if re.search(rf"\b{naam}\b", laag) and naam[:5] not in bron:
            uit.append(f"naam van een test niet in het gesprek: {naam.capitalize()}")
    if re.search(r"\b(beiderzijds|bilateraal|bdz)\b", laag) and not re.search(r"beiderzijds|bilateraal|beide kanten|allebei|aan beide", bron):
        uit.append("beiderzijds niet in het gesprek")
    for zijde, vormen in _ZIJDE.items():
        in_soep = any(re.search(rf"\b{v.strip()}\b", laag) for v in vormen)
        in_gesprek = any(v.strip() in bron for v in vormen[:3])
        if in_soep and not in_gesprek:
            uit.append(f"zijde niet in het gesprek: {zijde}")
    for naam, in_soep, in_gesprek in _ONDERWERPEN:
        if re.search(in_soep, laag) and not re.search(in_gesprek, bron):
            uit.append(f"onderwerp niet besproken: {naam}")
    if _VANGNET_SOEP.search(soep) and not _VANGNET_GESPREK.search(gesprek):
        uit.append("vangnet of controle niet in het gesprek afgesproken")
    if re.search(r"(?<!worden )(?<!kan )\buitgesloten\b", laag):
        uit.append('"uitgesloten": in een verslag liever "geen aanwijzingen voor"')
    if _AFGEBROKEN.search(_soep_tekst(problemen)):
        uit.append("afgebroken zin (er is iets uit geknipt)")
    uit.extend(icpc_controle.controleer_delen(problemen))
    return list(dict.fromkeys(uit))


def toets_valkuilen(problemen: List[dict], toets: dict) -> dict:
    """The known pitfalls of a test consult as hard checks: what must not and what must be in it."""
    soep = _soep_tekst(problemen) + "\n" + " ".join(f"{p.get('icpc_code', '')} {p.get('icpc_titel', '')}" for p in problemen)

    def tekst(regel: dict) -> str:   # "veld": only that part of the report (e.g. E)
        veld = regel.get("veld")
        return "\n".join(str(p.get(veld) or "") for p in problemen) if veld else soep

    fout = [r["uitleg"] for r in toets.get("mag_niet", []) if re.search(r["regex"], tekst(r), re.IGNORECASE)]
    fout += [r["uitleg"] for r in toets.get("moet", []) if not re.search(r["regex"], tekst(r), re.IGNORECASE)]
    if not any(str(p.get("e") or "").strip() for p in problemen):
        fout.append("E is leeg")
    totaal = len(toets.get("mag_niet", [])) + len(toets.get("moet", [])) + 1
    return {"gehaald": totaal - len(fout), "totaal": totaal, "fout": fout}


EU_MODELLEN = {"medium": "mistral-medium-latest", "large": "mistral-large-latest"}


class SoepTestVraag(BaseModel):
    id: Optional[str] = None
    gesprek: str = Field("", max_length=MAX_GESPREK)
    taal: Optional[str] = "nl"
    eu_model: Optional[str] = None          # "medium" | "large"; empty = the server setting
    controle: bool = False                  # also run the EU report through the control pass
    run: Optional[str] = Field(None, max_length=60, pattern=r"^[\w:.-]*$")   # groups the rows of one testset run


LOG_DEEL = 3000   # characters per log line for a submission


def _log_rapport(run: Optional[str], consult: str, rol: str, model: str, r: dict) -> None:
    """The full report of a testset consult (acted, no patient) into the log."""
    logger.info("soeptest.rapport", run=run or "", consult=consult, rol=rol, model=model,
                seconden=r.get("seconden"), fout=r.get("fout", ""),
                valkuilen=r.get("valkuilen", {}), verdacht=r.get("verdacht", []),
                markeringen=r.get("markeringen", []),
                verslag=json.dumps(r.get("problemen", []), ensure_ascii=False))


class Inzending(BaseModel):
    titel: str = Field(..., min_length=1, max_length=200)
    bron: str = Field("", max_length=500)
    duur_seconden: int = Field(0, ge=0, le=36000)
    gesprek: str = Field(..., min_length=50, max_length=MAX_GESPREK)


async def _een(gesprek: str, aanbieder: str, taal: Optional[str], model: Optional[str] = None,
               toets: Optional[dict] = None) -> dict:
    start = time.monotonic()
    try:
        verbeterd, _ = correct_transcript_full(gesprek)
        leren.zet_eigenaar("")   # the test set measures the system, not one doctor's style
        soep = await pipeline.genereer_soep(verbeterd, aanbieder, taal, model=model)
    except Exception as exc:  # one failing model does not hide the other
        logger.warning("soeptest.fout", aanbieder=aanbieder, error=type(exc).__name__)
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {"aanbieder": aanbieder, "fout": detail[:300], "seconden": round(time.monotonic() - start, 1)}
    delen = soep.problemen or [{k: getattr(soep, k) for k in pipeline.SOEP_VELDEN}]
    uit = {"aanbieder": aanbieder, "seconden": round(time.monotonic() - start, 1),
           "problemen": delen, "verdacht": verdacht(delen, gesprek)}
    if toets:
        uit["valkuilen"] = toets_valkuilen(delen, toets)
    return uit


async def _gecontroleerd(gesprek: str, eerste: dict, aanbieder: str, model: Optional[str],
                         toets: Optional[dict]) -> dict:
    """The first EU report with the markings of the control pass
    (pipeline.controleer_soep). The report itself is not changed."""
    if "problemen" not in eerste:
        return {"aanbieder": aanbieder, "fout": "Geen eerste verslag om te controleren.", "seconden": 0}
    start = time.monotonic()
    try:
        verbeterd, _ = correct_transcript_full(gesprek)
        soep = pipeline.SOEPResult(**pipeline.soep_met_problemen({"problemen": eerste["problemen"]}))
        markeringen = await pipeline.controleer_soep(verbeterd, soep, aanbieder, model=model)
    except Exception as exc:
        logger.warning("soeptest.controle_fout", error=type(exc).__name__)
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return {"aanbieder": aanbieder, "fout": detail[:300], "seconden": round(time.monotonic() - start, 1)}
    return dict(eerste, seconden=round(eerste.get("seconden", 0) + time.monotonic() - start, 1),
                markeringen=markeringen)


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
    model = EU_MODELLEN.get((vraag.eu_model or "").lower()) if eu == "mistral" else None
    consult = next((c for c in index() if c["id"] == vraag.id), {}) if vraag.id else {}
    toets = consult.get("toets")
    claude, mistral = await asyncio.gather(_een(gesprek, "anthropic", vraag.taal, toets=toets),
                                           _een(gesprek, eu, vraag.taal, model=model, toets=toets))
    gecontroleerd = await _gecontroleerd(gesprek, mistral, eu, model, toets) if vraag.controle else None
    await register.log(door, "beheer.soeptest", consult=vraag.id or "eigen", claude_ok="problemen" in claude,
                       eu_ok="problemen" in mistral, verdacht_claude=len(claude.get("verdacht", [])),
                       verdacht_eu=len(mistral.get("verdacht", [])))
    eu_naam = model or (get_config().llm.mistral_quality_model if eu == "mistral" else eu)
    uit = {"claude": claude, "eu": mistral, "eu_model": eu_naam, "valkuilen": consult.get("valkuilen", [])}
    if gecontroleerd is not None:
        uit["eu_gecontroleerd"] = gecontroleerd
    if vraag.id:   # only the fixed testset: acted consults
        _log_rapport(vraag.run, vraag.id, "claude", "claude", claude)
        _log_rapport(vraag.run, vraag.id, "eu", eu_naam, mistral)
        if gecontroleerd is not None:
            _log_rapport(vraag.run, vraag.id, "eu+controle", eu_naam, gecontroleerd)
    return uit


@router.post("/api/v1/beheer/testset/inzending")
async def inzending(vraag: Inzending, door: str = Depends(vereis_beheerder)):
    """An acted consult from the speech test, into the log in parts, to be added to the testset."""
    ident = uuid.uuid4().hex[:8]
    delen = [vraag.gesprek[i:i + LOG_DEEL] for i in range(0, len(vraag.gesprek), LOG_DEEL)]
    for nr, tekst in enumerate(delen, 1):
        logger.info("testset.inzending", inzending=ident, deel=nr, delen=len(delen), titel=vraag.titel,
                    bron=vraag.bron, duur_seconden=vraag.duur_seconden, tekst=tekst)
    await register.log(door, "beheer.testset_inzending", inzending=ident, delen=len(delen))
    return {"id": ident, "delen": len(delen)}


def vaste_markeringen(problemen: List[dict], gesprek: str) -> List[dict]:
    """The fixed check (verdacht) as markings for the doctor, next to the
    language model's: free, deterministic, and in the test runs rarely wrong.
    Where the finding names a fragment that is in the report, it is marked in
    the text; otherwise it is only listed."""
    uit: List[dict] = []
    for melding in verdacht(problemen, gesprek):
        if melding.startswith("afgebroken zin"):
            continue   # only meaningful after cutting, which the live path never does
        term = melding.rsplit(": ", 1)[1] if ": " in melding else ""
        plek = None
        if term:
            for nr, deel in enumerate(problemen):
                for veld in ("s", "o", "e", "p"):
                    if term.lower() in str(deel.get(veld) or "").lower():
                        plek = (nr, veld)
                        break
                if plek:
                    break
        if plek:
            uit.append({"probleem": plek[0], "veld": plek[1], "tekst": term, "reden": melding, "bron": "vast"})
        else:
            uit.append({"probleem": 0, "veld": "", "tekst": "", "reden": melding, "bron": "vast"})
    return uit
