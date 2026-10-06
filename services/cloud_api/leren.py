"""
VitaScribe Cloud API - Leren per arts

Het taalmodel zelf leert niet van het gebruik (de afspraak met de aanbieders
is juist: niets bewaren, niet trainen). Wat leert, is wat VitaScribe het model
meegeeft, per arts:

  soep   stijlregels: hoe deze arts een verslag schrijft ("geen 'patiënt
         geeft aan'", "lateraliteit als li/re"). Gaan mee in elke SOEP-opdracht.
  woord  woorden die de spraakherkenning verkeerd verstond en hoe ze horen
         (medicijnen, termen). Gaan mee als woordenlijst voor Voxtral en
         Deepgram, en in de SOEP-opdracht.
  tolk   afspraken per taal: hoe je iets zegt zodat deze patiënten het
         begrijpen. Gaan mee in elke vertaling.
  econsult  schrijfstijl van antwoorden op e-consulten: aanhef, toon,
         afsluiting, lengte. Gaan mee in elk concept-antwoord.

De bron is wat de arts verandert: het verschil tussen het concept en wat er in
Bricks komt, en in de tolk de beurten die eenvoudiger moesten. Dat verschil
wordt nooit bewaard. Het taalmodel haalt er meteen algemene regels uit, zonder
patiëntgegevens; alleen die regels worden bewaard, en een stijl- of tolkregel
gaat pas mee als de arts hem goedkeurt. Een woord gaat vanzelf mee als het
drie keer zo verbeterd is.

Daarnaast alleen getallen per dag (vs_leermeting): hoeveel procent de arts
aanpaste, hoe vaak de tolk het eenvoudiger moest zeggen. Daaraan is te zien
of het leren werkt.

Opslag: het register (PostgreSQL) als dat aan staat, anders in het geheugen
van de server (weg bij een herstart).

Endpoints (API-sleutel verplicht; alles van de arts zelf):
  POST /api/v1/leren/soep       {concept, definitief, markeringen}
  POST /api/v1/leren/tolk       {taal, eenvoudiger: [{voor, na}], weggehaald, beurten}
  POST /api/v1/leren/econsult   {concept, definitief}
  GET  /api/v1/leren/overzicht  -> regels en meting
  POST /api/v1/leren/regel      {soort, taal?, regel? | van, naar}   (zelf toevoegen)
  POST /api/v1/leren/regel/{id} {status: actief | afgewezen | weg}
"""

from __future__ import annotations

import difflib
import json
import re
import time
from contextvars import ContextVar
from datetime import date, timedelta
from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import audit, data_policy, llm_service, register
from .auth import verify_api_key

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/leren", tags=["leren"])

SOORTEN = ("soep", "woord", "tolk", "econsult")
STATUSSEN = ("voorstel", "actief", "afgewezen")
MAX_ACTIEF = {"soep": 25, "woord": 60, "tolk": 30, "econsult": 20}
WOORD_VANZELF = 3            # zo vaak dezelfde verbetering: dan gaat het woord vanzelf mee
MIN_GEWIJZIGD = 2.0          # minder dan 2% veranderd: niets te leren, alleen meten
MAX_REGEL = 200
MAX_VELD = 6000
CACHE_SEC = 60

# Who is asking: set by licentie.identificeer for every request and WebSocket.
_eigenaar: ContextVar[str] = ContextVar("vs_leren_eigenaar", default="")


def zet_eigenaar(wie: str) -> None:
    _eigenaar.set(wie or "")


def eigenaar() -> str:
    return _eigenaar.get()


# ── Storage ──

def _sleutel(soort: str, regel: str, van: str = "") -> str:
    tekst = van if soort == "woord" else regel
    return " ".join(re.sub(r"[^\w]+", " ", tekst.lower()).split())[:200]


class _Geheugen:
    """Without a register: in memory (lost on a restart; fine for tests and one server)."""

    def __init__(self) -> None:
        self.regels: List[dict] = []
        self.meting: Dict[tuple, dict] = {}
        self.volgende = 1

    async def bewaar(self, wie: str, soort: str, taal: str, regel: str, van: str, naar: str, status: str) -> dict:
        sl = _sleutel(soort, regel, van)
        for r in self.regels:
            if (r["eigenaar"], r["soort"], r["taal"], r["sleutel"]) == (wie, soort, taal, sl):
                r["aantal"] += 1
                if r["status"] == "voorstel" and status == "actief":
                    r["status"] = "actief"
                if soort == "woord" and r["status"] == "voorstel" and r["aantal"] >= WOORD_VANZELF:
                    r["status"] = "actief"
                r["bijgewerkt"] = time.time()
                return dict(r)
        r = {"id": self.volgende, "eigenaar": wie, "soort": soort, "taal": taal, "sleutel": sl, "regel": regel,
             "van": van, "naar": naar, "status": status, "aantal": 1, "bijgewerkt": time.time()}
        self.volgende += 1
        self.regels.append(r)
        return dict(r)

    async def lijst(self, wie: str, soort: Optional[str] = None, taal: Optional[str] = None,
                    status: Optional[str] = None) -> List[dict]:
        uit = [dict(r) for r in self.regels if r["eigenaar"] == wie
               and (soort is None or r["soort"] == soort) and (taal is None or r["taal"] == taal)
               and (status is None or r["status"] == status)]
        return sorted(uit, key=lambda r: -r["bijgewerkt"])

    async def zet_status(self, wie: str, regel_id: int, status: str) -> bool:
        for r in list(self.regels):
            if r["id"] == regel_id and r["eigenaar"] == wie:
                if status == "weg":
                    self.regels.remove(r)
                else:
                    r["status"] = status
                return True
        return False

    async def meet(self, wie: str, soort: str, **getallen: float) -> None:
        k = (wie, date.today().isoformat(), soort)
        m = self.meting.setdefault(k, {"eigenaar": wie, "dag": k[1], "soort": soort, "aantal": 0, "gewijzigd": 0.0,
                                       "markeringen": 0, "eenvoudiger": 0, "weggehaald": 0})
        m["aantal"] += 1
        for naam, waarde in getallen.items():
            m[naam] += waarde

    async def metingen(self, wie: str, dagen: int) -> List[dict]:
        vanaf = (date.today() - timedelta(days=dagen)).isoformat()
        return sorted((dict(m) for m in self.meting.values() if m["eigenaar"] == wie and m["dag"] >= vanaf),
                      key=lambda m: (m["dag"], m["soort"]))


class _Register:
    async def bewaar(self, wie: str, soort: str, taal: str, regel: str, van: str, naar: str, status: str) -> dict:
        rij = await register.fetchrow(
            """INSERT INTO vs_leren (eigenaar, soort, taal, sleutel, regel, van, naar, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (eigenaar, soort, taal, sleutel) DO UPDATE SET
                 aantal = vs_leren.aantal + 1, bijgewerkt = now(),
                 status = CASE
                   WHEN vs_leren.status = 'voorstel' AND EXCLUDED.status = 'actief' THEN 'actief'
                   WHEN vs_leren.soort = 'woord' AND vs_leren.status = 'voorstel'
                        AND vs_leren.aantal + 1 >= $9 THEN 'actief'
                   ELSE vs_leren.status END
               RETURNING id, soort, taal, regel, van, naar, status, aantal""",
            wie, soort, taal, _sleutel(soort, regel, van), regel, van, naar, status, WOORD_VANZELF)
        return dict(rij)

    async def lijst(self, wie: str, soort: Optional[str] = None, taal: Optional[str] = None,
                    status: Optional[str] = None) -> List[dict]:
        rijen = await register.fetch(
            """SELECT id, soort, taal, regel, van, naar, status, aantal FROM vs_leren
               WHERE eigenaar = $1 AND ($2::text IS NULL OR soort = $2) AND ($3::text IS NULL OR taal = $3)
                 AND ($4::text IS NULL OR status = $4)
               ORDER BY bijgewerkt DESC""", wie, soort, taal, status)
        return [dict(r) for r in rijen]

    async def zet_status(self, wie: str, regel_id: int, status: str) -> bool:
        if status == "weg":
            uit = await register.execute("DELETE FROM vs_leren WHERE id = $1 AND eigenaar = $2", regel_id, wie)
        else:
            uit = await register.execute("UPDATE vs_leren SET status = $3, bijgewerkt = now() WHERE id = $1 AND eigenaar = $2",
                                         regel_id, wie, status)
        return not uit.endswith(" 0")

    async def meet(self, wie: str, soort: str, **getallen: float) -> None:
        g = {k: getallen.get(k, 0) for k in ("gewijzigd", "markeringen", "eenvoudiger", "weggehaald")}
        await register.execute(
            """INSERT INTO vs_leermeting (eigenaar, dag, soort, aantal, gewijzigd, markeringen, eenvoudiger, weggehaald)
               VALUES ($1, CURRENT_DATE, $2, 1, $3, $4, $5, $6)
               ON CONFLICT (eigenaar, dag, soort) DO UPDATE SET aantal = vs_leermeting.aantal + 1,
                 gewijzigd = vs_leermeting.gewijzigd + $3, markeringen = vs_leermeting.markeringen + $4,
                 eenvoudiger = vs_leermeting.eenvoudiger + $5, weggehaald = vs_leermeting.weggehaald + $6""",
            wie, soort, float(g["gewijzigd"]), int(g["markeringen"]), int(g["eenvoudiger"]), int(g["weggehaald"]))

    async def metingen(self, wie: str, dagen: int) -> List[dict]:
        rijen = await register.fetch(
            """SELECT dag::text AS dag, soort, aantal, gewijzigd, markeringen, eenvoudiger, weggehaald
               FROM vs_leermeting WHERE eigenaar = $1 AND dag >= CURRENT_DATE - $2::int ORDER BY dag, soort""",
            wie, dagen)
        return [dict(r) for r in rijen]


_geheugen = _Geheugen()


def opslag():
    return _Register() if register.actief() else _geheugen


# ── What goes along with the model ──

_cache: Dict[tuple, tuple] = {}


async def actief(soort: str, taal: str = "") -> List[dict]:
    wie = eigenaar()
    if not wie:
        return []
    k = (wie, soort, taal)
    if k in _cache and time.time() - _cache[k][0] < CACHE_SEC:
        return _cache[k][1]
    try:
        regels = (await opslag().lijst(wie, soort, taal, "actief"))[:MAX_ACTIEF[soort]]
    except Exception as exc:   # learning must never block a report
        logger.warning("leren.lees_fout", error=type(exc).__name__)
        regels = []
    _cache[k] = (time.time(), regels)
    return regels


def _vergeet(wie: str) -> None:
    for k in [k for k in _cache if k[0] == wie]:
        _cache.pop(k, None)


async def huisstijl_prompt() -> str:
    """Line for the SOEP prompt: this doctor's style rules and spellings."""
    regels = await actief("soep")
    woorden = await actief("woord")
    delen = []
    if regels:
        delen.append("HUISSTIJL VAN DEZE ARTS (alleen vorm en woordkeus; voeg nooit inhoud toe die niet in het "
                     "gesprek staat):\n" + "\n".join(f"- {r['regel']}" for r in regels))
    if woorden:
        delen.append("JUISTE SPELLING (de spraakherkenning hoort deze woorden soms verkeerd):\n"
                     + "\n".join(f"- {r['van']} → {r['naar']}" for r in woorden))
    return ("\n\n".join(delen) + "\n\n") if delen else ""


async def woordenlijst() -> List[str]:
    """Learned words for the speech recognition (Voxtral context_bias, Deepgram keyterms)."""
    return [r["naar"] for r in await actief("woord") if r.get("naar")]


def met_woorden(geleerd: List[str], van_extensie) -> list:
    """Learned words first, then the keyterms the extension sent (whatever shape)."""
    return list(geleerd) + (list(van_extensie) if isinstance(van_extensie, list) else [])


async def tolk_prompt(taal: str) -> str:
    regels = await actief("tolk", taal)
    if not regels:
        return ""
    return ("\nAFSPRAKEN VAN DEZE ARTS VOOR DEZE TAAL (eerder gebleken wat patiënten begrijpen):\n"
            + "\n".join(f"- {r['regel']}" for r in regels) + "\n")


async def econsult_prompt() -> str:
    """Line for the e-consult prompt: how this doctor writes to patients."""
    regels = await actief("econsult")
    if not regels:
        return ""
    return ("SCHRIJFSTIJL VAN DEZE ARTS IN E-CONSULTANTWOORDEN (alleen aanhef, toon, woordkeus, lengte en "
            "afsluiting; voeg nooit medisch advies toe dat de arts niet gaf):\n"
            + "\n".join(f"- {r['regel']}" for r in regels) + "\n\n")


# ── Learning from what the doctor changed ──

def gewijzigd_pct(concept: Dict[str, str], definitief: Dict[str, str]) -> float:
    a = "\n".join(str(concept.get(k) or "") for k in "soep")
    b = "\n".join(str(definitief.get(k) or "") for k in "soep")
    if not a and not b:
        return 0.0
    return round((1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()) * 100, 1)


SOEP_LEER_SYSTEM = """Je helpt een huisarts zijn verslagsoftware te verbeteren. Je krijgt een SOEP-concept dat de software schreef en de versie die de arts na aanpassen in het dossier zette.

Leid hieruit af wat de software in het vervolg anders moet doen bij DEZE arts:
1. "regels": algemene stijlregels die de arts kennelijk hanteert, bijvoorbeeld over woordkeus, afkortingen, volgorde, wat in welke rubriek hoort, of wat hij weglaat. Alleen regels die voor elk volgend consult gelden.
2. "woorden": woorden die de spraakherkenning verkeerd verstond en die de arts verbeterde: "van" zoals het in het concept stond, "naar" zoals het hoort. Alleen medische termen, medicijnnamen, namen van instellingen of plaatsen; nooit namen van personen.

Strikt:
- Geen enkel gegeven van deze patiënt: geen naam, leeftijd, klacht, diagnose, waarde, datum of medicijn als feit over deze patiënt. Een regel als "noem de bloeddruk in O" mag; "patiënt heeft hypertensie" niet.
- Een inhoudelijke correctie van één feit (de arts verbeterde een getal of een zijde) is geen regel; sla die over.
- Liever geen regel dan een twijfelachtige. Maximaal 3 regels en 5 woorden. Kort, in het Nederlands, als opdracht ("Schrijf …", "Gebruik …", "Zet …").

Antwoord alleen met JSON: {"regels": ["..."], "woorden": [{"van": "...", "naar": "..."}]}"""

TOLK_LEER_SYSTEM = """Je helpt een huisarts een AI-tolk te verbeteren voor patiënten die {taal} spreken. Je krijgt zinnen die de arts eenvoudiger liet zeggen: eerst de vertaling die te moeilijk was, dan de eenvoudigere.

Leid algemene afspraken af voor volgende gesprekken in deze taal, bijvoorbeeld welk woord patiënten wel begrijpen voor een medisch begrip, of welke zinsbouw werkt. Schrijf ze in het Nederlands, met het woord in de doeltaal erbij ("Zeg voor 'bloeddruk' in het {taal}: …").

Strikt: geen gegevens van deze patiënt. Liever geen afspraak dan een twijfelachtige. Maximaal 3.

Antwoord alleen met JSON: {{"regels": ["..."]}}"""


ECONSULT_LEER_SYSTEM = """Je helpt een huisarts zijn software voor e-consulten te verbeteren. Je krijgt een concept-antwoord aan een patiënt dat de software schreef, en de versie die de arts na aanpassen verstuurde.

Leid hieruit af hoe deze arts in het vervolg wil dat zijn antwoorden aan patiënten klinken: aanhef en afsluiting, u of je, lengte, toon (zakelijk of warm), opbouw, woorden die hij vermijdt of juist gebruikt, of hij een termijn of vangnet ("bel als ...") noemt.

Strikt:
- Alleen vorm, toon en opbouw. Geen medische inhoud, geen advies, geen dosering: die verschillen per patiënt.
- Geen enkel gegeven van deze patiënt: geen naam, klacht, diagnose, medicijn, datum of waarde.
- Een inhoudelijke verbetering van één feit is geen regel; sla die over.
- Liever geen regel dan een twijfelachtige. Maximaal 3. Kort, in het Nederlands, als opdracht ("Begin met …", "Spreek de patiënt aan met …").

Antwoord alleen met JSON: {"regels": ["..."]}"""


def _parse(tekst: str) -> dict:
    tekst = (tekst or "").strip()
    try:
        return json.loads(tekst)
    except json.JSONDecodeError:
        a, b = tekst.find("{"), tekst.rfind("}")
        return json.loads(tekst[a:b + 1]) if a != -1 and b > a else {}


def schoon(tekst: str, max_len: int = MAX_REGEL) -> str:
    """A rule as it is stored: one line, with the privacy safety net over it."""
    from .letters import privacy_safety_net
    tekst = " ".join(str(tekst or "").split())[:max_len]
    tekst = privacy_safety_net(tekst)
    # A date or a long number has no place in a general rule.
    if re.search(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b|\d{6,}|\[(BSN|DATUM|NAAM|TELEFOON|EMAIL|POSTCODE|IBAN)", tekst):
        return ""
    return tekst


async def _voorstellen(wie: str, soort: str, taal: str, regels: List[str], woorden: List[dict]) -> List[dict]:
    o = opslag()
    uit = []
    for r in regels[:3]:
        tekst = schoon(r)
        if len(tekst) >= 8:
            rij = await o.bewaar(wie, soort, taal, tekst, "", "", "voorstel")
            if rij["status"] == "voorstel":
                uit.append(rij)
    for w in woorden[:5]:
        van, naar = schoon(w.get("van", ""), 60), schoon(w.get("naar", ""), 60)
        if van and naar and van.lower() != naar.lower():
            rij = await o.bewaar(wie, "woord", "", f"{van} → {naar}", van, naar, "voorstel")
            if rij["status"] == "voorstel":
                uit.append(rij)
    _vergeet(wie)
    return [{k: r[k] for k in ("id", "soort", "taal", "regel", "van", "naar", "status", "aantal")} for r in uit]


class SoepVeld(BaseModel):
    s: str = Field(default="", max_length=MAX_VELD)
    o: str = Field(default="", max_length=MAX_VELD)
    e: str = Field(default="", max_length=MAX_VELD)
    p: str = Field(default="", max_length=MAX_VELD)


class SoepLeren(BaseModel):
    concept: SoepVeld
    definitief: SoepVeld
    markeringen: int = Field(default=0, ge=0, le=100)


@router.post("/soep")
async def leer_soep(body: SoepLeren, user: str = Depends(verify_api_key)):
    wie = eigenaar() or f"naam:{user}"
    concept, definitief = body.concept.model_dump(), body.definitief.model_dump()
    pct = gewijzigd_pct(concept, definitief)
    await opslag().meet(wie, "soep", gewijzigd=pct, markeringen=body.markeringen)
    voorstellen: List[dict] = []
    if pct >= MIN_GEWIJZIGD:
        user_prompt = ("CONCEPT VAN DE SOFTWARE:\n" + "\n".join(f"{k.upper()}: {concept[k]}" for k in "soep")
                       + "\n\nDEFINITIEF DOOR DE ARTS:\n" + "\n".join(f"{k.upper()}: {definitief[k]}" for k in "soep"))
        try:
            data = _parse(await llm_service.complete(SOEP_LEER_SYSTEM, user_prompt, provider=data_policy.phi_llm_provider(),
                                                     json_mode=True, max_tokens=600))
            voorstellen = await _voorstellen(wie, "soep", "", list(data.get("regels") or []),
                                             [w for w in data.get("woorden") or [] if isinstance(w, dict)])
        except Exception as exc:   # learning is a bonus; never an error for the doctor
            logger.warning("leren.soep_fout", error=type(exc).__name__)
    logger.info("leren.soep", gewijzigd=pct, voorstellen=len(voorstellen))
    audit.log_event(user, "leren.soep", gewijzigd=pct, voorstellen=len(voorstellen))
    return {"gewijzigd_pct": pct, "voorstellen": voorstellen}


class Eenvoudiger(BaseModel):
    voor: str = Field(..., max_length=2000)
    na: str = Field(..., max_length=2000)


class TolkLeren(BaseModel):
    taal: str = Field(..., max_length=10)
    beurten: int = Field(default=0, ge=0, le=1000)
    eenvoudiger: List[Eenvoudiger] = Field(default_factory=list, max_length=20)
    weggehaald: int = Field(default=0, ge=0, le=1000)


@router.post("/tolk")
async def leer_tolk(body: TolkLeren, user: str = Depends(verify_api_key)):
    from .tolk import TALEN
    taal = TALEN.get(body.taal)
    if not taal or taal.code == "nl":
        raise HTTPException(status_code=400, detail="Onbekende taal.")
    wie = eigenaar() or f"naam:{user}"
    await opslag().meet(wie, "tolk", eenvoudiger=len(body.eenvoudiger), weggehaald=body.weggehaald)
    voorstellen: List[dict] = []
    if body.eenvoudiger:
        paren = "\n\n".join(f"TE MOEILIJK: {e.voor}\nEENVOUDIGER: {e.na}" for e in body.eenvoudiger)
        try:
            data = _parse(await llm_service.complete(TOLK_LEER_SYSTEM.format(taal=taal.naam), paren,
                                                     provider=data_policy.phi_llm_provider(), json_mode=True,
                                                     max_tokens=500))
            voorstellen = await _voorstellen(wie, "tolk", taal.code, list(data.get("regels") or []), [])
        except Exception as exc:
            logger.warning("leren.tolk_fout", error=type(exc).__name__)
    logger.info("leren.tolk", taal=taal.code, eenvoudiger=len(body.eenvoudiger), weggehaald=body.weggehaald,
                voorstellen=len(voorstellen))
    audit.log_event(user, "leren.tolk", taal=taal.code, voorstellen=len(voorstellen))
    return {"voorstellen": voorstellen}


class EconsultLeren(BaseModel):
    concept: str = Field(..., max_length=MAX_VELD)
    definitief: str = Field(..., max_length=MAX_VELD)


@router.post("/econsult")
async def leer_econsult(body: EconsultLeren, user: str = Depends(verify_api_key)):
    wie = eigenaar() or f"naam:{user}"
    pct = gewijzigd_pct({"s": body.concept}, {"s": body.definitief})
    await opslag().meet(wie, "econsult", gewijzigd=pct)
    voorstellen: List[dict] = []
    if pct >= MIN_GEWIJZIGD:
        user_prompt = f"CONCEPT VAN DE SOFTWARE:\n{body.concept}\n\nVERSTUURD DOOR DE ARTS:\n{body.definitief}"
        try:
            data = _parse(await llm_service.complete(ECONSULT_LEER_SYSTEM, user_prompt,
                                                     provider=data_policy.phi_llm_provider(),
                                                     json_mode=True, max_tokens=500))
            voorstellen = await _voorstellen(wie, "econsult", "", list(data.get("regels") or []), [])
        except Exception as exc:   # learning is a bonus; never an error for the doctor
            logger.warning("leren.econsult_fout", error=type(exc).__name__)
    logger.info("leren.econsult", gewijzigd=pct, voorstellen=len(voorstellen))
    audit.log_event(user, "leren.econsult", gewijzigd=pct, voorstellen=len(voorstellen))
    return {"gewijzigd_pct": pct, "voorstellen": voorstellen}


@router.get("/overzicht")
async def overzicht(user: str = Depends(verify_api_key)):
    wie = eigenaar() or f"naam:{user}"
    o = opslag()
    regels = await o.lijst(wie)
    return {
        "regels": [{k: r[k] for k in ("id", "soort", "taal", "regel", "van", "naar", "status", "aantal")}
                   for r in regels if r["status"] != "afgewezen"],
        "afgewezen": sum(1 for r in regels if r["status"] == "afgewezen"),
        "meting": await o.metingen(wie, 120),
        "opslag": "register" if register.actief() else "geheugen",
    }


class NieuweRegel(BaseModel):
    soort: str = Field(..., pattern="^(soep|woord|tolk|econsult)$")
    taal: str = Field(default="", max_length=10)
    regel: str = Field(default="", max_length=MAX_REGEL)
    van: str = Field(default="", max_length=60)
    naar: str = Field(default="", max_length=60)


@router.post("/regel")
async def nieuwe_regel(body: NieuweRegel, user: str = Depends(verify_api_key)):
    wie = eigenaar() or f"naam:{user}"
    if body.soort == "woord":
        van, naar = schoon(body.van, 60), schoon(body.naar, 60)
        if not (van and naar):
            raise HTTPException(status_code=400, detail="Vul in hoe het verstaan wordt en hoe het hoort.")
        rij = await opslag().bewaar(wie, "woord", "", f"{van} → {naar}", van, naar, "actief")
    else:
        regel = schoon(body.regel)
        if len(regel) < 8:
            raise HTTPException(status_code=400, detail="Schrijf de regel iets uitgebreider, zonder patiëntgegevens.")
        rij = await opslag().bewaar(wie, body.soort, body.taal if body.soort == "tolk" else "", regel, "", "", "actief")
    _vergeet(wie)
    audit.log_event(user, "leren.regel", soort=body.soort, status="actief")
    return {k: rij[k] for k in ("id", "soort", "taal", "regel", "van", "naar", "status", "aantal")}


class Status(BaseModel):
    status: str = Field(..., pattern="^(actief|afgewezen|weg)$")


@router.post("/regel/{regel_id}")
async def zet_status(regel_id: int, body: Status, user: str = Depends(verify_api_key)):
    wie = eigenaar() or f"naam:{user}"
    if not await opslag().zet_status(wie, regel_id, body.status):
        raise HTTPException(status_code=404, detail="Regel niet gevonden.")
    _vergeet(wie)
    audit.log_event(user, "leren.regel", status=body.status)
    return {"ok": True}
