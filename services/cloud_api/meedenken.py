"""
VitaScribe Cloud API - Meedenken bij de SOEP

Na elke SOEP kijkt een tweede, korte aanroep op de achtergrond mee:

1. Medicatie herkennen (altijd): spraakherkenning verhaspelt geneesmiddel-
   namen. Elk middel in S en P krijgt de juiste Nederlandse stofnaam (zoals
   in het Farmacotherapeutisch Kompas); een herkenningsfout krijgt een
   voorstel om te vervangen. Dat is verslaglegging, geen advies.
2. Meedenken met het beleid (NHG): ligt P in lijn met de standaard die bij
   de werkdiagnose in E hoort, en hooguit drie korte voorstellen.
3. Voor de patiënt: onderwerpen voor Thuisarts.nl (zoektermen, nooit URL's).

2 en 3 zijn klinische beslissingsondersteuning (MDR regel 11). Ze draaien
alleen als de server het toestaat (CLINICAL_DECISION_SUPPORT) én de arts het
in de extensie heeft aangezet; anders vraagt de prompt er niet eens om.

De arts beslist: niets wordt in de SOEP gezet zonder klik. Een vervangvoorstel
geldt alleen als de genoemde tekst letterlijk in de SOEP staat (de server
controleert dat), zodat de knop nooit iets anders verandert dan bedoeld.

Endpoint (API-sleutel verplicht):
  POST /api/v1/soep/meedenken  {soep: {s,o,e,p,icpc_code,icpc_titel}, cds} -> voorstellen
"""

from __future__ import annotations

import json
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import audit, data_policy, llm_service
from .auth import verify_api_key
from .letters import privacy_safety_net

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/soep", tags=["meedenken"])

MAX_VELD = 4000
MAX_MEDICATIE = 10
MAX_SUGGESTIES = 3
MAX_THUISARTS = 2
MAX_TOKENS = 1000
OORDELEN = ("in_lijn", "deels", "afwijkend", "onbekend")

_MEDICATIE = """\
TAAK 1 — MEDICATIE HERKENNEN
- Zoek elk geneesmiddel in S en P (ook merknamen, afkortingen en verhaspelde \
  namen uit spraakherkenning).
- "veld": "s" of "p", waar het staat.
- "genoemd": de tekst EXACT zoals die in de SOEP staat, letterlijk \
  overgenomen (alleen de naam, of naam met sterkte als die er direct bij staat).
- "middel": de juiste Nederlandse stofnaam zoals in het Farmacotherapeutisch \
  Kompas en de G-Standaard (bij een merknaam: stofnaam).
- "vervang": alleen als "genoemd" een herkenningsfout of verkeerde \
  schrijfwijze bevat: hoe het er correct uitziet (zelfde sterkte en \
  dosering). Anders een lege string.
- "zeker": true als je zeker weet welk middel bedoeld is; bij twijfel false \
  en "vervang" leeg. Verzin geen middelen."""

_OPMERKING_MET = """\
- "opmerking": alleen bij iets dat uit de SOEP zelf blijkt: een duidelijk \
  ongebruikelijke dosering, dubbelmedicatie, of een bekende interactie of \
  contra-indicatie met iets dat in S of O staat. Eén korte zin; anders leeg."""

_OPMERKING_ZONDER = """\
- "opmerking": altijd een lege string."""

_BELEID = """\
TAAK 2 — MEEDENKEN MET HET BELEID (NHG)
- Neem de werkdiagnose in E als uitgangspunt. Stel zelf geen andere diagnose.
- Vergelijk P met de NHG-Standaard die daarbij hoort. "oordeel": \
  "in_lijn", "deels" (in lijn, maar iets wezenlijks ontbreekt of wijkt af), \
  "afwijkend", of "onbekend" (geen passende standaard of te weinig informatie).
- "richtlijn": de naam, bijv. "NHG-Standaard Urineweginfecties"; anders leeg.
- "toelichting": hooguit één korte zin, alleen bij "deels" of "afwijkend".
- "suggesties": hooguit 3 korte, concrete voorstellen die de arts kan \
  overwegen (bijv. "Urinekweek bij recidief binnen een jaar", "Vangnetadvies \
  bij koorts of flankpijn"). Niet herhalen wat al in P staat. Formuleer als \
  voorstel, niet als correctie. Liever geen suggestie dan een zwakke.
- Patiëntfactoren (zwangerschap, nierfunctie, leeftijd, allergie) alleen \
  meewegen als ze in de SOEP staan.

TAAK 3 — VOOR DE PATIËNT
- "thuisarts": hooguit 2 zoektermen voor een passende pagina op \
  Thuisarts.nl (bijv. "blaasontsteking"). Geen URL's. Leeg als niets past."""

_ZONDER_BELEID = """\
Taak 2 en 3 vervallen: "beleid" krijgt oordeel "onbekend" en verder lege \
velden, en "thuisarts" is een lege lijst."""


def system_prompt(cds: bool) -> str:
    return "\n\n".join([
        "Je bent een ervaren Nederlandse huisarts met kennis van het "
        "Farmacotherapeutisch Kompas en de NHG-Standaarden. Je kijkt op de "
        "achtergrond mee met een SOEP-regel die een collega net heeft "
        "gedicteerd; de tekst komt uit spraakherkenning. De collega beslist; "
        "jij doet alleen voorstellen. Wees kort en schrijf in het Nederlands.",
        _MEDICATIE + "\n" + (_OPMERKING_MET if cds else _OPMERKING_ZONDER),
        _BELEID if cds else _ZONDER_BELEID,
    ])


SCHEMA = {
    "type": "object",
    "properties": {
        "medicatie": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "veld": {"type": "string", "enum": ["s", "p"]},
                    "genoemd": {"type": "string"},
                    "middel": {"type": "string"},
                    "vervang": {"type": "string"},
                    "zeker": {"type": "boolean"},
                    "opmerking": {"type": "string"},
                },
                "required": ["veld", "genoemd", "middel", "vervang", "zeker", "opmerking"],
                "additionalProperties": False,
            },
        },
        "beleid": {
            "type": "object",
            "properties": {
                "oordeel": {"type": "string", "enum": list(OORDELEN)},
                "richtlijn": {"type": "string"},
                "toelichting": {"type": "string"},
                "suggesties": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["oordeel", "richtlijn", "toelichting", "suggesties"],
            "additionalProperties": False,
        },
        "thuisarts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["medicatie", "beleid", "thuisarts"],
    "additionalProperties": False,
}


class Soep(BaseModel):
    s: str = Field("", max_length=MAX_VELD)
    o: str = Field("", max_length=MAX_VELD)
    e: str = Field("", max_length=MAX_VELD)
    p: str = Field("", max_length=MAX_VELD)
    icpc_code: Optional[str] = Field("", max_length=20)
    icpc_titel: Optional[str] = Field("", max_length=200)


class MeedenkenRequest(BaseModel):
    soep: Soep
    cds: bool = False


def _parse(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.split("\n") if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _tekst(v) -> str:
    return str(v or "").strip()


def schoon_medicatie(items, soep: dict, cds: bool) -> List[dict]:
    """Keep what the UI can act on safely. A replacement only stands when the
    quoted text occurs literally in its field; otherwise the button could
    change something else than the doctor sees."""
    uit = []
    for m in items or []:
        if not isinstance(m, dict) or len(uit) >= MAX_MEDICATIE:
            continue
        veld = m.get("veld") if m.get("veld") in ("s", "p") else "p"
        genoemd, vervang, middel = _tekst(m.get("genoemd")), _tekst(m.get("vervang")), _tekst(m.get("middel"))
        if not genoemd or not middel:
            continue
        gevonden = genoemd.lower() in soep.get(veld, "").lower()
        if not gevonden:
            ander = "p" if veld == "s" else "s"
            if genoemd.lower() in soep.get(ander, "").lower():
                veld, gevonden = ander, True
        zeker = bool(m.get("zeker"))
        if not gevonden or not zeker or vervang.lower() == genoemd.lower():
            vervang = ""
        uit.append({
            "veld": veld, "genoemd": genoemd, "middel": middel, "vervang": vervang,
            "zeker": zeker, "opmerking": _tekst(m.get("opmerking")) if cds else "",
        })
    return uit


@router.post("/meedenken")
async def meedenken(body: MeedenkenRequest, user: str = Depends(verify_api_key)):
    """Medication check always; policy and patient information only with
    clinical decision support allowed by the server and chosen by the doctor."""
    soep = {k: privacy_safety_net(_tekst(getattr(body.soep, k))) for k in ("s", "o", "e", "p")}
    if not (soep["s"] or soep["p"] or soep["e"]):
        raise HTTPException(status_code=400, detail="Geen SOEP om mee te denken.")
    cds = bool(body.cds) and data_policy.clinical_decision_support()
    icpc = " ".join(x for x in (_tekst(body.soep.icpc_code), _tekst(body.soep.icpc_titel)) if x)
    user_prompt = "\n".join(
        [f"{k.upper()}: {soep[k] or '-'}" for k in ("s", "o", "e", "p")]
        + ([f"ICPC: {icpc}"] if icpc else [])
    )
    provider = data_policy.phi_llm_provider()
    try:
        raw = await llm_service.complete(
            system_prompt(cds), user_prompt, provider=provider, json_mode=True,
            max_tokens=MAX_TOKENS, quality=True, json_schema=SCHEMA,
        )
        data = _parse(raw)
    except ValueError as exc:   # includes json.JSONDecodeError
        logger.warning("soep.meedenken.failed", error=str(exc)[:200])
        raise HTTPException(status_code=502, detail="Meedenken lukte nu niet.")
    except Exception as exc:  # network, provider 4xx/5xx
        logger.warning("soep.meedenken.failed", error=type(exc).__name__)
        raise HTTPException(status_code=502, detail="De AI-dienst reageert niet.")

    medicatie = schoon_medicatie(data.get("medicatie"), soep, cds)
    beleid, thuisarts = None, []
    if cds:
        b = data.get("beleid") if isinstance(data.get("beleid"), dict) else {}
        oordeel = b.get("oordeel") if b.get("oordeel") in OORDELEN else "onbekend"
        beleid = {
            "oordeel": oordeel,
            "richtlijn": _tekst(b.get("richtlijn")),
            "toelichting": _tekst(b.get("toelichting")) if oordeel in ("deels", "afwijkend") else "",
            "suggesties": [_tekst(x) for x in (b.get("suggesties") or []) if _tekst(x)][:MAX_SUGGESTIES],
        }
        thuisarts = [_tekst(x) for x in (data.get("thuisarts") or [])
                     if _tekst(x) and "/" not in _tekst(x)][:MAX_THUISARTS]
    logger.info("soep.meedenken", cds=cds, medicatie=len(medicatie),
                vervang=sum(1 for m in medicatie if m["vervang"]),
                oordeel=beleid["oordeel"] if beleid else "")
    audit.log_event(user, "soep.meedenken", provider=provider, mode="cds" if cds else "medicatie",
                    status=beleid["oordeel"] if beleid else "")
    return {"cds": cds, "medicatie": medicatie, "beleid": beleid, "thuisarts": thuisarts}
