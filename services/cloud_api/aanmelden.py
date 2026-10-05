"""
VitaScribe Cloud API - Aanmelden door een praktijk

  GET  /aanmelden           het formulier (static/aanmelden.html)
  POST /api/v1/aanmelden    de aanmelding

Een aanmelding maakt een praktijk met status 'aangemeld' en licentietype
'kandidaat'. Er gebeurt verder niets vanzelf: pas als de beheerder de praktijk
activeert en gebruikers aanmaakt, kan de praktijk VitaScribe gebruiken.

Wat er gevraagd wordt is het minimum om een praktijk te kunnen beoordelen en te
bellen: naam en plaats, het Bricks-praktijknummer, een contactpersoon, het
aantal huisarts-FTE en werkplekken. Geen patiëntgegevens.

Tegen misbruik: een verborgen veld dat een mens niet invult, hooguit vijf
aanmeldingen per adres per uur en vijftig per dag in totaal.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from . import data_policy, licentie, register

logger = structlog.get_logger()
router = APIRouter(tags=["aanmelden"])
STATIC = Path(__file__).parent / "static"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_per_adres: Dict[str, List[float]] = {}
_totaal: List[float] = []


class Aanmelding(BaseModel):
    model_config = {"extra": "forbid"}
    praktijknaam: str = Field(..., min_length=2, max_length=200)
    plaats: str = Field(..., min_length=2, max_length=100)
    praktijknummer: str = Field("", max_length=40)
    agb: str = Field("", max_length=20)
    contact_naam: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., max_length=200)
    telefoon: str = Field("", max_length=40)
    fte: Optional[float] = Field(None, ge=0, le=999)
    werkplekken: Optional[int] = Field(None, ge=0, le=9999)
    opmerking: str = Field("", max_length=2000)
    akkoord: bool = False
    website: str = Field("", max_length=200)   # verborgen veld: een mens laat het leeg


def _adres(request: Request) -> str:
    kop = request.headers.get("x-forwarded-for", "")
    if kop:
        return kop.split(",")[-1].strip()   # het deel dat de proxy van Railway toevoegt
    return request.client.host if request.client else "?"


def _limiet(adres: str) -> None:
    nu = time.time()
    lijst = [t for t in _per_adres.get(adres, []) if nu - t < 3600]
    _totaal[:] = [t for t in _totaal if nu - t < 86400]
    if len(lijst) >= 5 or len(_totaal) >= 50:
        raise HTTPException(status_code=429, detail="Er zijn te veel aanmeldingen tegelijk binnengekomen. "
                                                    "Probeer het later opnieuw of mail ons.")
    lijst.append(nu)
    _per_adres[adres] = lijst
    _totaal.append(nu)


GESLOTEN = ("Aanmelden is gesloten: VitaScribe wordt nu alleen intern gebruikt, in de eigen praktijk. "
            "Wilt u op de hoogte blijven, mail ons dan.")


@router.get("/aanmelden", include_in_schema=False)
async def aanmeldpagina():
    if data_policy.fase() == "intern":
        return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>VitaScribe</title>"
                            f"<p style='font-family:sans-serif;max-width:36em;margin:3em auto'>{GESLOTEN}</p>",
                            status_code=404)
    return FileResponse(STATIC / "aanmelden.html", headers={
        "Cache-Control": "no-cache",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
    })


@router.get("/aanmelden/aanmelden.js", include_in_schema=False)
async def aanmeldscript():
    return FileResponse(STATIC / "aanmelden.js", headers={"Cache-Control": "no-cache"})


@router.post("/api/v1/aanmelden")
async def aanmelden(invoer: Aanmelding, request: Request):
    if data_policy.fase() == "intern":
        raise HTTPException(status_code=403, detail=GESLOTEN)
    if not register.actief():
        raise HTTPException(status_code=503, detail="Aanmelden kan op dit moment niet. Mail ons liever.")
    if invoer.website:
        # Een robot. Doe alsof het gelukt is, dan probeert hij het niet anders.
        return {"ok": True}
    if not invoer.akkoord:
        raise HTTPException(status_code=400, detail="Ga akkoord met de voorwaarden voor de testfase.")
    email = invoer.email.strip()
    if not EMAIL.match(email):
        raise HTTPException(status_code=400, detail="Vul een geldig e-mailadres in.")
    nummers = [n for n in re.split(r"[\s,;]+", invoer.praktijknummer.strip()) if n]
    for n in nummers:
        if not licentie.PRAKTIJKNUMMER.match(n):
            raise HTTPException(status_code=400, detail="Het praktijknummer bestaat uit 3 tot 6 cijfers. "
                                                        "U vindt het in de adresbalk van Bricks, na de schuine streep.")
    _limiet(_adres(request))

    rij = await register.fetchrow(
        """
        INSERT INTO vs_praktijken (naam, plaats, praktijknummers, agb, contact_naam, contact_email, telefoon,
                                   fte, werkplekken, opmerking_aanmelding)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id
        """,
        invoer.praktijknaam.strip(), invoer.plaats.strip(), nummers[:4], invoer.agb.strip(),
        invoer.contact_naam.strip(), email, invoer.telefoon.strip(), invoer.fte, invoer.werkplekken,
        invoer.opmerking.strip(),
    )
    await register.log("aanmeldformulier", "praktijk.aangemeld", rij["id"], naam=invoer.praktijknaam.strip())
    logger.info("aanmelden.nieuw", praktijk_id=rij["id"])
    return {"ok": True}
