"""
VitaScribe Cloud API - Licentiestatus en eigen sleutels van de praktijk

  GET    /api/v1/licentie                     wat de extensie over de licentie toont
  PUT    /api/v1/praktijk/sleutels/{dienst}   eigen sleutel opslaan (praktijkbeheerder)
  DELETE /api/v1/praktijk/sleutels/{dienst}   eigen sleutel verwijderen (praktijkbeheerder)

Wat er met een eigen sleutel mag, is vastgelegd met de praktijkhouder
(26-09-2026) en staat hier hard, niet in een instelling:

- 'brieven' (Anthropic of OpenAI) wordt alleen gebruikt voor brieven. Die zijn
  in de browser en op de server gepseudonimiseerd. Dictaat, SOEP, consultverslag
  en schermafdrukken gaan nooit over een eigen sleutel: die blijven bij het
  EU-model van de server (data_policy.phi_llm_provider).
- 'spraak' (Deepgram) wordt gebruikt voor dicteren en consultopnames, via het
  EU-eindpunt en met modeltraining uit, net als de sleutel van de server.

De sleutel gaat één keer van de extensie naar de server, wordt gecontroleerd bij
de aanbieder en versleuteld opgeslagen (kluis.py). Hij komt nooit meer terug
naar een browser; de extensie ziet alleen de laatste vier tekens.

Heeft de praktijk geen eigen sleutel, dan loopt alles via de sleutels van de
server, tenzij de beheerder 'eigen sleutels verplicht' heeft aangezet.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import audit, data_policy, kluis, licentie, register
from .auth import huidige_identiteit
from .config import get_config

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["licentie"])

AANBIEDERS = {"brieven": ("anthropic", "openai"), "spraak": ("deepgram",)}
SLEUTELVORM = re.compile(r"^[A-Za-z0-9_\-\.]{20,300}$")


# ── Welke sleutel geldt voor deze aanroep ──

async def _eigen(praktijk_id: int, dienst: str) -> Optional[Tuple[str, str]]:
    rij = await register.fetchrow(
        "SELECT aanbieder, versleuteld FROM vs_praktijk_sleutels WHERE praktijk_id = $1 AND dienst = $2",
        praktijk_id, dienst,
    )
    if not rij:
        return None
    geheim = kluis.ontsleutel(rij["versleuteld"])
    if geheim is None:
        logger.error("praktijk_sleutel.onleesbaar", praktijk_id=praktijk_id, dienst=dienst)
        raise HTTPException(status_code=503, detail="De eigen sleutel van de praktijk is op de server niet te lezen. "
                                                    "Stel hem opnieuw in bij Instellingen.")
    return rij["aanbieder"], geheim


async def kies_brieven(ident: licentie.Identiteit) -> Tuple[str, Optional[str]]:
    """(aanbieder, sleutel) voor een brief. Sleutel None = die van de server.
    Heeft de praktijk gekozen voor brieven in de EU, dan gaat die keuze voor:
    ook een eigen sleutel bij een aanbieder in de VS wordt dan niet gebruikt.
    Draait de server de patiëntgegevens al in de EU (Bedrock), dan gaan de
    brieven daar ook heen; anders naar Mistral."""
    if ident.brieven_in_eu:
        eu = data_policy.phi_llm_provider()
        return (eu if eu in data_policy.EU_PROVIDERS else "mistral"), None
    if ident.bron == "register" and ident.praktijk_id:
        eigen = await _eigen(ident.praktijk_id, "brieven")
        if eigen:
            return eigen
        if ident.eigen_sleutels_verplicht:
            raise HTTPException(status_code=403, detail="Uw praktijk schrijft brieven met een eigen AI-sleutel. "
                                                        "De praktijkbeheerder stelt die in bij Instellingen, onder Eigen AI-sleutels.")
    return data_policy.letters_llm_provider(), None


async def kies_spraak(ident: licentie.Identiteit) -> str:
    """De Deepgram-sleutel voor deze aanroep."""
    if ident.bron == "register" and ident.praktijk_id:
        eigen = await _eigen(ident.praktijk_id, "spraak")
        if eigen:
            return eigen[1]
        if ident.eigen_sleutels_verplicht:
            raise HTTPException(status_code=403, detail="Uw praktijk gebruikt voor spraak een eigen Deepgram-sleutel. "
                                                        "De praktijkbeheerder stelt die in bij Instellingen, onder Eigen AI-sleutels.")
    return get_config().stt.deepgram_api_key


# ── Controle bij de aanbieder ──

def _deepgram_basis() -> str:
    host = urlparse(get_config().dictation.deepgram_url).hostname or "api.eu.deepgram.com"
    return f"https://{host}"


async def controleer_bij_aanbieder(aanbieder: str, sleutel: str) -> Optional[str]:
    """None als de aanbieder de sleutel accepteert, anders een melding.
    Vervangbaar in tests; roept alleen een lijst op, verbruikt niets."""
    if aanbieder == "anthropic":
        url, kop = "https://api.anthropic.com/v1/models", {"x-api-key": sleutel, "anthropic-version": "2023-06-01"}
    elif aanbieder == "openai":
        url, kop = "https://api.openai.com/v1/models", {"Authorization": f"Bearer {sleutel}"}
    else:
        url, kop = f"{_deepgram_basis()}/v1/projects", {"Authorization": f"Token {sleutel}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            antwoord = await client.get(url, headers=kop)
    except httpx.HTTPError:
        return "De aanbieder was niet bereikbaar om de sleutel te controleren. Probeer het straks opnieuw."
    if antwoord.status_code in (401, 403):
        return "De aanbieder kent deze sleutel niet of heeft hem ingetrokken."
    if antwoord.status_code >= 400:
        return f"De aanbieder gaf fout {antwoord.status_code} bij het controleren van de sleutel."
    return None


CONTROLE = controleer_bij_aanbieder


# ── Eindpunten ──

async def _status_sleutels(praktijk_id: int) -> dict:
    rijen = await register.fetch(
        "SELECT dienst, aanbieder, hint, ingesteld_op FROM vs_praktijk_sleutels WHERE praktijk_id = $1",
        praktijk_id,
    )
    uit = {"brieven": None, "spraak": None}
    for r in rijen:
        uit[r["dienst"]] = {"aanbieder": r["aanbieder"], "hint": r["hint"],
                            "ingesteld_op": r["ingesteld_op"].isoformat()}
    return uit


@router.get("/licentie")
async def licentie_status(ident: licentie.Identiteit = Depends(huidige_identiteit)):
    """Voor de instellingen van de extensie: voor wie, tot wanneer, welke sleutels."""
    uit = {
        "bron": ident.bron,
        "gebruiker": ident.gebruiker_naam or ident.label,
        "rol": ident.rol,
        "praktijk": ident.praktijk_naam,
        "licentietype": ident.licentietype,
        "geldig_tot": ident.geldig_tot.isoformat() if ident.geldig_tot else None,
        "praktijknummers": ident.praktijknummers,
        "eigen_sleutels_mogelijk": ident.bron == "register" and kluis.actief(),
        "eigen_sleutels_verplicht": ident.eigen_sleutels_verplicht,
        "brieven_in_eu": ident.brieven_in_eu,
        "eigen_sleutels": {"brieven": None, "spraak": None},
    }
    if ident.bron == "register" and ident.praktijk_id:
        uit["eigen_sleutels"] = await _status_sleutels(ident.praktijk_id)
    return uit


class SleutelInvoer(BaseModel):
    model_config = {"extra": "forbid"}
    aanbieder: str = Field(..., max_length=20)
    sleutel: str = Field(..., min_length=20, max_length=300)


def _alleen_praktijkbeheerder(ident: licentie.Identiteit) -> None:
    if ident.bron != "register" or not ident.praktijk_id:
        raise HTTPException(status_code=400, detail="Eigen sleutels horen bij een praktijk met een licentie.")
    if not ident.is_praktijkbeheerder:
        raise HTTPException(status_code=403, detail="Alleen de praktijkbeheerder kan de eigen sleutels van de praktijk wijzigen.")


@router.put("/praktijk/sleutels/{dienst}")
async def sleutel_opslaan(dienst: str, invoer: SleutelInvoer,
                          ident: licentie.Identiteit = Depends(huidige_identiteit)):
    _alleen_praktijkbeheerder(ident)
    if dienst not in AANBIEDERS:
        raise HTTPException(status_code=404, detail="Onbekende dienst.")
    aanbieder = invoer.aanbieder.strip().lower()
    if aanbieder not in AANBIEDERS[dienst]:
        raise HTTPException(status_code=400, detail=f"Voor {dienst} kan dat alleen: {', '.join(AANBIEDERS[dienst])}.")
    sleutel = invoer.sleutel.strip()
    if not SLEUTELVORM.match(sleutel):
        raise HTTPException(status_code=400, detail="Dit ziet er niet uit als een API-sleutel. Plak hem zonder spaties.")
    if not kluis.actief():
        raise HTTPException(status_code=503, detail="Eigen sleutels zijn op deze server niet ingeschakeld.")

    fout = await CONTROLE(aanbieder, sleutel)
    if fout:
        raise HTTPException(status_code=400, detail=fout)

    await register.execute(
        """
        INSERT INTO vs_praktijk_sleutels (praktijk_id, dienst, aanbieder, versleuteld, hint, ingesteld_door)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (praktijk_id, dienst) DO UPDATE
           SET aanbieder = EXCLUDED.aanbieder, versleuteld = EXCLUDED.versleuteld, hint = EXCLUDED.hint,
               ingesteld_door = EXCLUDED.ingesteld_door, ingesteld_op = now()
        """,
        ident.praktijk_id, dienst, aanbieder, kluis.versleutel(sleutel), licentie.hint(sleutel), ident.gebruiker_id,
    )
    await register.log(ident.label, "praktijk.sleutel_ingesteld", ident.praktijk_id, dienst=dienst, aanbieder=aanbieder)
    audit.log_event(ident.label, "praktijk.sleutel", kind=dienst, provider=aanbieder, status="ingesteld")
    return await _status_sleutels(ident.praktijk_id)


@router.delete("/praktijk/sleutels/{dienst}")
async def sleutel_verwijderen(dienst: str, ident: licentie.Identiteit = Depends(huidige_identiteit)):
    _alleen_praktijkbeheerder(ident)
    if dienst not in AANBIEDERS:
        raise HTTPException(status_code=404, detail="Onbekende dienst.")
    await register.execute("DELETE FROM vs_praktijk_sleutels WHERE praktijk_id = $1 AND dienst = $2",
                           ident.praktijk_id, dienst)
    await register.log(ident.label, "praktijk.sleutel_verwijderd", ident.praktijk_id, dienst=dienst)
    audit.log_event(ident.label, "praktijk.sleutel", kind=dienst, status="verwijderd")
    return await _status_sleutels(ident.praktijk_id)
