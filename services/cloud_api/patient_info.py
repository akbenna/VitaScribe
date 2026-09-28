"""
VitaScribe Cloud API - Patiëntinstructie (B1 en vertaling)

Turns the doctor's E and P lines into a short explanation for the patient in
plain Dutch (B1) and, optionally, a translation. Only what the doctor wrote
is rephrased: no new advice, diagnoses or doses. Always a draft the doctor
checks. Runs on the patient-data language model (data_policy.phi_llm_provider).

  POST /api/v1/patient-instructions
"""

from __future__ import annotations

from typing import Literal, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import audit, data_policy, llm_service
from .auth import verify_api_key
from .pipeline import _parse_json_response

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["patient"])

LANGUAGES = {
    "": None,
    "en": "Engels",
    "ar": "Arabisch (Modern Standaard Arabisch)",
    "tr": "Turks",
    "pl": "Pools",
    "uk": "Oekraïens",
    "fr": "Frans",
    "de": "Duits",
    "es": "Spaans",
}

SYSTEM = """\
Je herschrijft het beleid van een Nederlandse huisarts naar een korte uitleg \
voor de patiënt.

REGELS
- Gebruik ALLEEN wat in E en P staat. Voeg geen adviezen, diagnoses, \
  onderzoeken, doseringen of termijnen toe. Staat iets er niet, dan noem je \
  het niet.
- Taalniveau B1: korte zinnen (max. 15 woorden), gewone woorden, spreek de \
  patiënt aan met "u". Leg een medische term in één zin uit.
- Opbouw met deze kopjes (laat een kopje weg als er niets bij hoort): \
  "Wat is er aan de hand", "Wat gaat u doen", "Uw medicijn", \
  "Wanneer belt u de praktijk".
- Medicijnen: naam, hoeveel, hoe vaak en hoe lang, precies zoals in P.
- Sluit af met: "Heeft u vragen? Bel de praktijk."
- Geen namen, geen markdown-opmaak, geen emoji.

Als er een vertaling gevraagd wordt: vertaal de Nederlandse tekst trouw, \
zonder iets toe te voegen of weg te laten. Medicijnnamen en getallen blijven \
gelijk.

ANTWOORD in JSON: {"nl": "...", "vertaling": "..."} ("vertaling" leeg als \
er geen taal gevraagd is)."""


class InstructionRequest(BaseModel):
    e: str = Field("", max_length=2000)
    p: str = Field(..., min_length=3, max_length=4000)
    taal: str = Field("", max_length=5)


@router.post("/patient-instructions")
async def patient_instructions(body: InstructionRequest, user: str = Depends(verify_api_key)):
    if body.taal not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Deze taal wordt niet ondersteund.")
    taal = LANGUAGES[body.taal]
    prompt = f"E (evaluatie): {body.e.strip() or '-'}\nP (plan): {body.p.strip()}\n\n" + (
        f"Vertaal daarnaast naar het {taal}." if taal else "Geen vertaling gevraagd."
    )
    provider = data_policy.phi_llm_provider()
    audit.log_event(user, "patient.instructions", provider=provider, kind=body.taal or "nl")
    try:
        raw = await llm_service.complete(
            system_prompt=SYSTEM, user_prompt=prompt, provider=provider,
            json_mode=True, max_tokens=1500, quality=True,
        )
        data = _parse_json_response(raw)
    except (ValueError, Exception) as exc:  # provider error or unparsable output
        logger.error("patient.instructions_error", error=str(exc)[:200])
        raise HTTPException(status_code=502, detail=f"Verwerking mislukt: {exc}")
    return {
        "nl": str(data.get("nl") or "").strip(),
        "vertaling": str(data.get("vertaling") or "").strip() if taal else "",
        "taal": taal or "",
    }
