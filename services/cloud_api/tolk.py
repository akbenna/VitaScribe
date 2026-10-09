"""
VitaScribe Cloud API - Tolk in de spreekkamer

Arts en patiënt spreken om beurten. Elke beurt is een korte opname: wie er
spreekt, weet de extensie (de arts drukt op zijn knop of die van de
patiënt), dus ook in welke taal. Per beurt:

  1. spraak naar tekst, in de taal van de spreker;
  2. vertalen naar de taal van de ander, als gesproken taal: korte zinnen,
     gewone woorden, namen, getallen en medicijnen ongewijzigd;
  3. de extensie leest de vertaling voor (/spreek: Voxtral TTS van Mistral,
     anders een stem die op de computer zelf staat).

Na het gesprek maakt /verslag er een SOEP van, uit de Nederlandse kant van
het gesprek, met dezelfde pipeline als een opgenomen consult (controleronde
en markeringen in de EU-modus inbegrepen).

De server bewaart niets: geen audio, geen tekst. Het auditlog krijgt alleen
wie, welke taal en hoe lang.

Welke talen kunnen, hangt af van de modus. In de EU-modus verstaat de
Europese spraakdienst (EU_STT_PROVIDER) de spraak. Voxtral (Mistral, de
standaard) kent geen Turks, Pools of Oekraïens; Gladia en Speechmatics
(werkplan stap 6) verstaan alle talen hieronder. In de Claude-modus verstaat Deepgram (EU-eindpunt) alle talen
hieronder, ook Marokkaans- en Syrisch-Arabisch als eigen dialect. Tigrinya
verstaat geen enkele dienst: daar typt de patiënt (tekst in /beurt).

Handsfree (spreker=auto): de beurt wordt in twee vaste talen verstaan
(Nederlands en die van de patiënt); het taalmodel kiest, met de beurtwisseling
als doorslag bij twijfel. De andere lezing gaat mee terug ("alternatief"), zodat
de arts een verkeerd gekozen spreker met één klik rechtzet.

Endpoints (API-sleutel verplicht):
  GET  /api/v1/tolk/talen                    -> talen en wat er per taal kan
  POST /api/v1/tolk/beurt   (multipart)      -> {origineel, vertaling, terugvertaling, onzeker, twijfel}
  POST /api/v1/tolk/spreek  {tekst, taal}    -> audio/mpeg, of 404 (de extensie leest dan zelf voor)
  POST /api/v1/tolk/verslag {taal, beurten}  -> zelfde vorm als /consult/process
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Dict, List, NamedTuple, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .mistral_adres import MISTRAL_API
from . import audit, data_policy, llm_service, stt_service
from .auth import huidige_identiteit, verify_api_key
from .config import get_config

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/tolk", tags=["tolk"])

MAX_BEURT_MB = 10            # een beurt duurt seconden tot een minuut
MAX_ZIN_CHARS = 2000
MAX_EERDER = 6               # vorige beurten als context (wie is "hij", welk medicijn)
MAX_BEURTEN = 400
MAX_SPREEK_CHARS = 1500
VERTAAL_MAX_TOKENS = 1200


class Taal(NamedTuple):
    code: str
    naam: str                 # Nederlands, voor de arts
    eigen: str                # in de taal zelf, voor de patiënt
    deepgram: Optional[str]   # Deepgram "language" (also Gladia/Speechmatics); None = no speech recognition knows it
    voxtral: Optional[str]    # Voxtral Transcribe; None = verstaat Voxtral niet
    tts: Optional[str]        # Voxtral TTS; None = alleen een stem op de computer
    prompt: str               # hoe het taalmodel de taal moet schrijven
    noot: str = ""            # beperking die de arts vooraf moet weten (kwaliteit, geen spraak)


TALEN: Dict[str, Taal] = {t.code: t for t in [
    Taal("nl", "Nederlands", "Nederlands", "nl", "nl", "nl", "Nederlands"),
    Taal("tr", "Turks", "Türkçe", "tr", None, None, "Turks"),
    Taal("pl", "Pools", "Polski", "pl", None, None, "Pools"),
    Taal("uk", "Oekraïens", "Українська", "uk", None, None, "Oekraïens"),
    Taal("ar", "Arabisch (standaard)", "العربية", "ar", "ar", "ar",
         "eenvoudig standaard-Arabisch, in Arabisch schrift"),
    Taal("ar-SY", "Syrisch-Arabisch", "الشامية", "ar-SY", "ar", "ar",
         "Syrisch (Levantijns) gesproken Arabisch, in Arabisch schrift; geen standaard-Arabisch"),
    Taal("ar-MA", "Marokkaans-Arabisch (Darija)", "الدارجة", "ar-MA", "ar", "ar",
         "Marokkaans gesproken Arabisch (Darija), in Arabisch schrift, zoals het in Marokko "
         "gesproken wordt; geen standaard-Arabisch"),
    Taal("de", "Duits", "Deutsch", "de", "de", "de", "Duits"),
    Taal("fr", "Frans", "Français", "fr", "fr", "fr", "Frans"),
    Taal("en", "Engels", "English", "en", "en", "en", "Engels"),
    # Geen spraakdienst kent Tigrinya, en geen stem leest het voor: de arts spreekt, de patiënt
    # leest de vertaling (Ge'ez-schrift) en typt zijn antwoord. De vertaling zelf is matig.
    Taal("ti", "Tigrinya", "ትግርኛ", None, None, None,
         "Tigrinya zoals in Eritrea gesproken, in Ge'ez-schrift (ፊደል); korte zinnen en de eenvoudigste woorden",
         noot="Tigrinya: de vertaling is van matige kwaliteit, de patiënt kan niet worden verstaan en er is geen "
              "stem om voor te lezen. De patiënt leest mee en typt zijn antwoord. Bij iets belangrijks: een "
              "professionele tolk."),
]}
ARTS_TAAL = TALEN["nl"]


def kies(code: Optional[str]) -> Taal:
    taal = TALEN.get(str(code or "").strip())
    if not taal or taal.code == "nl":
        raise HTTPException(status_code=400, detail="Kies de taal van de patiënt.")
    return taal


def verstaat(taal: Taal) -> bool:
    """Kan de spraakherkenning van deze modus deze taal verstaan? Gladia en
    Speechmatics (werkplan stap 6) verstaan de talen die Deepgram kent; Voxtral minder."""
    if taal.deepgram is None:
        return False
    if data_policy.eu_modus() and data_policy.eu_stt_provider() == "voxtral":
        return taal.voxtral is not None
    return True


async def talen_overzicht() -> List[dict]:
    uit = []
    for t in TALEN.values():
        if t.code == "nl":
            continue
        uit.append({
            "code": t.code, "naam": t.naam, "eigen": t.eigen,
            "verstaat": verstaat(t),
            "stem": await stem_bron(t),
            "waarom": "" if verstaat(t) else
                      f"Geen spraakherkenning verstaat {t.naam}; de patiënt kan zijn antwoord typen." if t.deepgram is None else
                      f"In de EU-modus verstaat de spraakherkenning (Voxtral, Mistral) geen {t.naam}. "
                      "Met Gladia of Speechmatics op de server wel.",
            "noot": t.noot,
        })
    return uit


@router.get("/talen")
async def talen(_user: str = Depends(verify_api_key)):
    return {"modus": data_policy.modus(), "talen": await talen_overzicht(),
            "nl_stem": await stem_bron(ARTS_TAAL)}


# ── 1 Spraak naar tekst, één beurt ──

async def _deepgram_beurt(audio: bytes, taal: Taal, sleutel: str, content_type: str) -> str:
    cfg = get_config()
    if not sleutel:
        raise ValueError("DEEPGRAM_API_KEY niet geconfigureerd.")
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            os.getenv("DEEPGRAM_URL", "https://api.eu.deepgram.com/v1/listen"),
            headers={"Authorization": f"Token {sleutel}", "Content-Type": content_type or "audio/webm"},
            params={"model": cfg.stt.deepgram_model, "language": taal.deepgram, "punctuate": "true",
                    "smart_format": "true", "mip_opt_out": "true"},
            content=audio,
        )
    if r.status_code != 200:
        logger.warning("tolk.deepgram_fout", status=r.status_code, body=r.text[:300], taal=taal.code)
        raise ValueError(f"Spraakherkenning gaf fout {r.status_code}.")
    data = r.json()
    duur = float((data.get("metadata") or {}).get("duration") or 0)
    logger.info("stt.usage", provider="deepgram", seconden=round(duur, 1), soort="beurt")
    from . import kosten
    kosten.tel("deepgram", "", "beurt", seconden=duur)
    kanalen = (data.get("results") or {}).get("channels") or [{}]
    alts = kanalen[0].get("alternatives") or [{}]
    return str(alts[0].get("transcript") or "").strip()


async def spraak_naar_tekst(audio: bytes, taal: Taal, deepgram_sleutel: Optional[str],
                            content_type: str = "audio/webm") -> str:
    """Vervangbaar in tests."""
    if data_policy.eu_modus():
        dienst = data_policy.eu_stt_provider()
        naam = "beurt.wav" if "wav" in (content_type or "") else "beurt.webm"
        res = await stt_service.transcribe_eu(audio, taal.voxtral if dienst == "voxtral" else taal.deepgram,
                                              naam=naam, diarize=False, provider=dienst)
        tekst = res.raw_text.strip()
        return stt_service.nederlandse_vulwoorden(tekst) if taal.code == "nl" else tekst
    return await _deepgram_beurt(audio, taal, deepgram_sleutel or "", content_type)


# ── 2 Vertalen ──

VERTAAL_SYSTEM = """Je bent een medisch tolk in een Nederlandse huisartsenpraktijk. Je vertaalt één gesproken beurt van {bron} naar {doel}. Wat je schrijft, wordt hardop voorgelezen.

Regels:
- Vertaal alles wat gezegd is. Laat niets weg en voeg niets toe. Geef geen antwoord, geen advies en geen eigen uitleg.
- Schrijf zoals je het hardop zegt: korte zinnen, gewone woorden, geen afkortingen, geen opsommingstekens.
- Spreek de ander beleefd aan (in het Nederlands met "u").
- Namen van personen, medicijnnamen, getallen, doseringen, datums en tijden neem je exact over.
- Vertaal je naar de patiënt: vervang een medische vakterm door gewone woorden die een leek begrijpt (bijvoorbeeld "hypertensie" wordt "hoge bloeddruk"), zonder de betekenis te veranderen.
- Vertaal je naar de arts: schrijf gewoon, correct Nederlands; laat de woorden van de patiënt zo dicht mogelijk bij wat gezegd is, ook als het vaag of onlogisch klinkt.
- De tekst komt uit spraakherkenning en kan verkeerd verstaan zijn. Vertaal dan wat het meest waarschijnlijk bedoeld is, zet "onzeker" op true en schrijf in "twijfel" in één korte Nederlandse zin wat onzeker is.
- "terugvertaling": jouw vertaling letterlijk terug in het Nederlands, zodat de arts kan controleren wat de patiënt hoort. Is de doeltaal Nederlands, laat het dan leeg.
{eenvoudiger}
Antwoord alleen met JSON: {{"vertaling": "...", "terugvertaling": "...", "onzeker": false, "twijfel": ""}}"""

EENVOUDIGER = ("- De arts vroeg om het eenvoudiger te zeggen: gebruik nog kortere zinnen en de "
               "eenvoudigste woorden, zonder iets van de inhoud weg te laten.\n")

VERTAAL_SCHEMA = {
    "type": "object",
    "properties": {
        "vertaling": {"type": "string"},
        "terugvertaling": {"type": "string"},
        "onzeker": {"type": "boolean"},
        "twijfel": {"type": "string"},
    },
    "required": ["vertaling", "terugvertaling", "onzeker", "twijfel"],
    "additionalProperties": False,
}


class Eerder(BaseModel):
    spreker: str = Field(..., pattern="^(arts|patient)$")
    nl: str = Field(..., max_length=MAX_ZIN_CHARS)


def vertaal_prompts(tekst: str, spreker: str, taal: Taal, eerder: List[Eerder],
                    eenvoudiger: bool = False, afspraken: str = "") -> "tuple[str, str]":
    bron, doel = (ARTS_TAAL, taal) if spreker == "arts" else (taal, ARTS_TAAL)
    system = VERTAAL_SYSTEM.format(bron=bron.prompt, doel=doel.prompt,
                                   eenvoudiger=(EENVOUDIGER if eenvoudiger else "") + afspraken)
    delen = []
    if eerder:
        regels = [f"{'Arts' if e.spreker == 'arts' else 'Patiënt'}: {e.nl.strip()}" for e in eerder[-MAX_EERDER:]]
        delen.append("EERDER IN HET GESPREK (Nederlands, alleen als context; niet vertalen):\n" + "\n".join(regels))
    wie = "DE ARTS" if spreker == "arts" else "DE PATIËNT"
    delen.append(f"TE VERTALEN, GEZEGD DOOR {wie}:\n{tekst.strip()}")
    return system, "\n\n".join(delen)


def _parse(tekst: str) -> dict:
    tekst = (tekst or "").strip()
    try:
        return json.loads(tekst)
    except json.JSONDecodeError:
        a, b = tekst.find("{"), tekst.rfind("}")
        if a != -1 and b > a:
            return json.loads(tekst[a:b + 1])
        raise


async def vertaal(tekst: str, spreker: str, taal: Taal, eerder: List[Eerder], eenvoudiger: bool = False) -> dict:
    from . import leren
    system, user = vertaal_prompts(tekst, spreker, taal, eerder, eenvoudiger, await leren.tolk_prompt(taal.code))
    raw = await llm_service.complete(system, user, provider=data_policy.phi_llm_provider(), json_mode=True,
                                     max_tokens=VERTAAL_MAX_TOKENS, json_schema=VERTAAL_SCHEMA)
    data = _parse(raw)
    naar_nl = spreker == "patient"
    return {
        "vertaling": str(data.get("vertaling") or "").strip(),
        "terugvertaling": "" if naar_nl else str(data.get("terugvertaling") or "").strip(),
        "onzeker": bool(data.get("onzeker")),
        "twijfel": str(data.get("twijfel") or "").strip(),
    }


VERTAAL_AUTO_SYSTEM = """Je bent een medisch tolk in een Nederlandse huisartsenpraktijk. De arts spreekt Nederlands, de patiënt spreekt {patient}. Je krijgt de spraakherkenning van één gesproken beurt{dubbel}. Wat je vertaalt, wordt hardop voorgelezen.

Stap 1, wie sprak: Nederlands is de arts, {patient} is de patiënt. Een herkenning in de verkeerde taal is meestal onzin of een rij losse woorden; kies de herkenning die een zinnige uiting is. Is het echt niet uit te maken (bijvoorbeeld alleen "ja" of "oké"), kies dan wat het best past bij het gesprek tot nu toe en zet "onzeker" op true.
Stap 2: zet in "origineel" de juiste herkende tekst, ongewijzigd, en in "spreker" "arts" of "patient".
Stap 3: vertaal. Van de arts naar {doel}; van de patiënt naar Nederlands.

Regels:
- Vertaal alles wat gezegd is. Laat niets weg en voeg niets toe. Geef geen antwoord, geen advies en geen eigen uitleg.
- Schrijf zoals je het hardop zegt: korte zinnen, gewone woorden, geen afkortingen, geen opsommingstekens.
- Spreek de ander beleefd aan (in het Nederlands met "u").
- Namen van personen, medicijnnamen, getallen, doseringen, datums en tijden neem je exact over.
- Naar de patiënt: vervang een medische vakterm door gewone woorden die een leek begrijpt, zonder de betekenis te veranderen.
- Naar de arts: correct Nederlands, zo dicht mogelijk bij wat de patiënt zei, ook als het vaag klinkt.
- Klinkt iets als verkeerd verstaan, vertaal dan wat het meest waarschijnlijk bedoeld is, zet "onzeker" op true en schrijf in "twijfel" in één korte Nederlandse zin wat onzeker is.
- "terugvertaling": alleen als de arts sprak, jouw vertaling letterlijk terug in het Nederlands; anders leeg.

Antwoord alleen met JSON: {{"spreker": "arts", "origineel": "...", "vertaling": "...", "terugvertaling": "...", "onzeker": false, "twijfel": ""}}"""

VERTAAL_AUTO_SCHEMA = {
    "type": "object",
    "properties": {
        "spreker": {"type": "string", "enum": ["arts", "patient"]},
        "origineel": {"type": "string"},
        **VERTAAL_SCHEMA["properties"],
    },
    "required": ["spreker", "origineel", *VERTAAL_SCHEMA["required"]],
    "additionalProperties": False,
}


async def kandidaten(audio: bytes, patient: Taal, sleutel: Optional[str],
                     content_type: str = "audio/webm") -> List["tuple[str, str]"]:
    """Hands-free: who spoke is not known. Only two languages are possible: Dutch
    (the doctor) and the patient's. The speech service hears the turn twice, as
    each of the two, at the same time; the language model then sees which of the
    two is a sensible utterance. Choosing from two instead of a hundred is what
    makes it reliable. Only when the EU service cannot be told the patient's
    language does it detect the language itself (one call). Replaceable in tests."""
    if data_policy.eu_modus() and not verstaat(patient):
        res = await stt_service.transcribe_eu(audio, None, naam="beurt.wav", diarize=False)
        return [("automatisch herkend", res.raw_text.strip())]
    import asyncio
    nl, ander = await asyncio.gather(
        spraak_naar_tekst(audio, ARTS_TAAL, sleutel, content_type),
        spraak_naar_tekst(audio, patient, sleutel, content_type),
        return_exceptions=True)
    uit = []
    for naam, r in ((NL_KANDIDAAT, nl), (f"verstaan als {patient.naam}", ander)):
        if isinstance(r, Exception):
            logger.warning("tolk.stt_fout", error=type(r).__name__, taal=naam)
            continue
        uit.append((naam, (r or "").strip()))
    if not uit:
        raise ValueError("Spraakherkenning mislukt.")
    return uit


def vertaal_auto_prompts(kand: List["tuple[str, str]"], patient: Taal, eerder: List[Eerder],
                         afspraken: str = "") -> "tuple[str, str]":
    dubbel = ", twee keer: " + " en ".join(n for n, _ in kand) if len(kand) > 1 else ""
    system = VERTAAL_AUTO_SYSTEM.format(patient=patient.naam, doel=patient.prompt, dubbel=dubbel) + afspraken
    delen = []
    if eerder:
        regels = [f"{'Arts' if e.spreker == 'arts' else 'Patiënt'}: {e.nl.strip()}" for e in eerder[-MAX_EERDER:]]
        delen.append("EERDER IN HET GESPREK (Nederlands, alleen als context; niet vertalen):\n" + "\n".join(regels))
    if eerder:
        # Turn-taking: in a conversation the speakers alternate. Only a tie-breaker.
        vorige, ander = ("de arts", "de patiënt") if eerder[-1].spreker == "arts" else ("de patiënt", "de arts")
        delen.append(f"BEURTWISSELING: de vorige beurt was van {vorige}. Meestal is nu {ander} aan de beurt; "
                     "laat dit alleen de doorslag geven als de herkenning zelf het niet uitmaakt.")
    for naam, tekst in kand:
        delen.append(f"HERKENNING ({naam}):\n{tekst or '(niets)'}")
    return system, "\n\n".join(delen)


NL_KANDIDAAT = "verstaan als Nederlands"


def alternatief(kand: List["tuple[str, str]"], spreker: str) -> Optional[dict]:
    """The other reading of a hands-free turn: what the speech service heard in
    the other language. With it, the doctor can fix a wrong choice of speaker
    with one click, without speaking again."""
    if len(kand) != 2:
        return None
    ander = "patient" if spreker == "arts" else "arts"
    for naam, tekst in kand:
        if (naam == NL_KANDIDAAT) == (ander == "arts") and tekst.strip():
            return {"spreker": ander, "origineel": tekst.strip()}
    return None


async def vertaal_auto(kand: List["tuple[str, str]"], patient: Taal, eerder: List[Eerder]) -> dict:
    from . import leren
    system, user = vertaal_auto_prompts(kand, patient, eerder, await leren.tolk_prompt(patient.code))
    raw = await llm_service.complete(system, user, provider=data_policy.phi_llm_provider(), json_mode=True,
                                     max_tokens=VERTAAL_MAX_TOKENS, json_schema=VERTAAL_AUTO_SCHEMA)
    data = _parse(raw)
    spreker = "arts" if data.get("spreker") == "arts" else "patient"
    origineel = str(data.get("origineel") or "").strip()
    if not origineel:   # the model left it out: take the transcript it most likely meant
        origineel = next((t for _, t in kand if t), "")
    return {
        "spreker": spreker,
        "origineel": origineel,
        "vertaling": str(data.get("vertaling") or "").strip(),
        "terugvertaling": str(data.get("terugvertaling") or "").strip() if spreker == "arts" else "",
        "onzeker": bool(data.get("onzeker")),
        "twijfel": str(data.get("twijfel") or "").strip(),
    }


def _toestemming(consent: bool, user: str) -> None:
    if os.getenv("REQUIRE_RECORDING_CONSENT", "true").lower() == "true" and not consent:
        audit.log_event(user, "tolk.refused", status="geen_toestemming")
        raise HTTPException(status_code=400, detail="Toestemming van de patiënt is niet bevestigd.")


def _eerder(veld: Optional[str]) -> List[Eerder]:
    if not veld:
        return []
    try:
        lijst = json.loads(veld)
        return [Eerder(**e) for e in lijst if isinstance(e, dict)][-MAX_EERDER:]
    except Exception:   # context is a nicety: a bad value never blocks a turn
        return []


@router.post("/beurt")
async def beurt(
    audio: Optional[UploadFile] = File(default=None),
    tekst: Optional[str] = Form(default=None, max_length=MAX_ZIN_CHARS),
    spreker: str = Form(..., pattern="^(arts|patient|auto)$"),
    taal: str = Form(...),
    consent: bool = Form(default=False),
    eerder: Optional[str] = Form(default=None),
    eenvoudiger: bool = Form(default=False),
    ident=Depends(huidige_identiteit),
):
    """Eén beurt: verstaan (of de tekst van een eerdere beurt opnieuw) en vertalen.
    spreker=auto (handsfree): de taal bepaalt wie er sprak."""
    user = ident.label
    _toestemming(consent, user)
    patient = kies(taal)
    auto = spreker == "auto"
    begin = time.time()
    context = _eerder(eerder)
    grootte = 0
    if tekst and tekst.strip():
        # "Zeg het eenvoudiger": the text is already there, no audio again.
        if auto:
            raise HTTPException(status_code=400, detail="Kies wie er sprak.")
        origineel = tekst.strip()
        kand: List["tuple[str, str]"] = []
    else:
        if audio is None:
            raise HTTPException(status_code=400, detail="Geen opname ontvangen.")
        if not verstaat(patient) and spreker != "arts":
            raise HTTPException(status_code=400, detail=f"In de EU-modus verstaat de spraakherkenning geen {patient.naam}.")
        inhoud = await audio.read()
        grootte = len(inhoud)
        if not inhoud:
            raise HTTPException(status_code=400, detail="Lege opname.")
        if grootte > MAX_BEURT_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Deze beurt is te lang; spreek in kortere stukken.")
        sleutel = None
        if not data_policy.eu_modus():
            from .praktijk_sleutels import kies_spraak
            sleutel = await kies_spraak(ident)
        soort = audio.content_type or "audio/webm"
        try:
            if auto:
                kand = await kandidaten(inhoud, patient, sleutel, soort)
                origineel = " ".join(t for _, t in kand).strip()
            else:
                bron = ARTS_TAAL if spreker == "arts" else patient
                origineel = await spraak_naar_tekst(inhoud, bron, sleutel, soort)
        except ValueError as exc:
            logger.warning("tolk.stt_fout", error=str(exc)[:200], taal=patient.code)
            raise HTTPException(status_code=502, detail="De spraak kon niet worden verstaan. Probeer het opnieuw.")
        except Exception as exc:
            logger.warning("tolk.stt_fout", error=type(exc).__name__, taal=patient.code)
            raise HTTPException(status_code=502, detail="De spraakherkenning reageert niet. Probeer het zo opnieuw.")
    if not origineel:
        audit.log_event(user, "tolk.beurt", spreker=spreker, taal=patient.code, status="leeg", bytes=grootte)
        return {"spreker": spreker, "origineel": "", "vertaling": "", "terugvertaling": "",
                "onzeker": False, "twijfel": "", "leeg": True}
    anders = None
    try:
        if auto:
            uit = await vertaal_auto(kand, patient, context)
            spreker, origineel = uit.pop("spreker"), uit.pop("origineel")
            anders = alternatief(kand, spreker)
        else:
            uit = await vertaal(origineel, spreker, patient, context, eenvoudiger)
    except ValueError as exc:   # includes json.JSONDecodeError
        logger.warning("tolk.vertaal_fout", error=str(exc)[:200])
        raise HTTPException(status_code=502, detail="De vertaling lukte niet. Probeer het opnieuw.")
    except Exception as exc:
        logger.warning("tolk.vertaal_fout", error=type(exc).__name__)
        raise HTTPException(status_code=502, detail="De AI-dienst reageert niet. Probeer het zo opnieuw.")
    # Content-free: who, which language, sizes and time.
    logger.info("tolk.beurt", spreker=spreker, auto=auto, taal=patient.code, bytes=grootte, chars=len(origineel),
                onzeker=uit["onzeker"], seconden=round(time.time() - begin, 1), modus=data_policy.modus())
    audit.log_event(user, "tolk.beurt", spreker=spreker, taal=patient.code, chars=len(origineel),
                    provider=data_policy.phi_llm_provider())
    return {"spreker": spreker, "origineel": origineel, **uit, "leeg": False, "alternatief": anders}


# ── 3 Voorlezen ──
#
# Best is a voice that speaks the language as its mother tongue. In order
# (TOLK_TTS_VOORKEUR, default azure,mistral,mistral_overig):
#   azure          Azure AI Speech, neural voices per country (ar-MA, ar-SY,
#                  tr-TR …). Microsoft (US company), EU region of choice; in the
#                  eu mode only when the practice allows it (TOLK_AZURE_IN_EU).
#   mistral        Voxtral TTS with a voice of that language: one the practice
#                  recorded itself (a colleague who speaks it natively reads 10
#                  to 20 seconds; Voxtral then speaks with that accent), or a
#                  Mistral voice of that language.
#   mistral_overig a Mistral voice of another language: a foreign accent, but
#                  in practice still better than the voices of Windows.
# Otherwise the extension reads aloud with a voice on the computer itself.

TTS_URL = f"{MISTRAL_API}/v1/audio/speech"
STEMMEN_URL = f"{MISTRAL_API}/v1/audio/voices"
_stemmen: Optional[List[dict]] = None

# Azure neural voices: (female, male). TOLK_AZURE_STEM_<CODE> overrides, e.g.
# TOLK_AZURE_STEM_AR_MA=ar-MA-JamalNeural.
AZURE_STEMMEN: Dict[str, "tuple[str, str]"] = {
    "nl": ("nl-NL-FennaNeural", "nl-NL-MaartenNeural"),
    "tr": ("tr-TR-EmelNeural", "tr-TR-AhmetNeural"),
    "pl": ("pl-PL-ZofiaNeural", "pl-PL-MarekNeural"),
    "uk": ("uk-UA-PolinaNeural", "uk-UA-OstapNeural"),
    "ar": ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural"),
    "ar-SY": ("ar-SY-AmanyNeural", "ar-SY-LaithNeural"),
    "ar-MA": ("ar-MA-MounaNeural", "ar-MA-JamalNeural"),
    "de": ("de-DE-KatjaNeural", "de-DE-ConradNeural"),
    "fr": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
    "en": ("en-GB-SoniaNeural", "en-GB-RyanNeural"),
}


def azure_stem(code: str, geslacht: str = "vrouw") -> Optional[str]:
    eigen = os.getenv("TOLK_AZURE_STEM_" + code.upper().replace("-", "_"))
    if eigen:
        return eigen
    paar = AZURE_STEMMEN.get(code)
    return (paar[1] if geslacht == "man" else paar[0]) if paar else None


def azure_mag() -> bool:
    if not (os.getenv("TOLK_AZURE_KEY") and os.getenv("TOLK_AZURE_REGION")):
        return False
    return not data_policy.eu_modus() or os.getenv("TOLK_AZURE_IN_EU", "false").lower() == "true"


def voorkeur() -> List[str]:
    return [v.strip() for v in os.getenv("TOLK_TTS_VOORKEUR", "azure,mistral,mistral_overig").lower().split(",") if v.strip()]


def _stem_id(stem: dict) -> str:
    for k in ("id", "voice_id", "slug", "name"):
        if stem.get(k):
            return str(stem[k])
    return ""


def _stem_talen(stem: dict) -> List[str]:
    talen = stem.get("languages") or stem.get("language") or stem.get("locale") or []
    return [talen] if isinstance(talen, str) else [str(t) for t in talen]


def kies_stem(stemmen: List[dict], taal: str) -> Optional[str]:
    """A Mistral voice of this language (it names the language, or has it as a
    prefix such as "fr_marie_neutral"), or None. Never a voice of another
    language: that reads with a foreign accent."""
    for s in stemmen:
        if any(t.lower().replace("_", "-").split("-")[0] == taal for t in _stem_talen(s)):
            return _stem_id(s)
    for s in stemmen:
        if re.match(rf"{re.escape(taal)}[_-]", _stem_id(s).lower()):
            return _stem_id(s)
    return None


STEMMEN_PAGINA = 100   # voices per page asked for
STEMMEN_MAX_PAGINAS = 20


def _stemmen_uit(body) -> List[dict]:
    lijst = body if isinstance(body, list) else (body.get("items") or body.get("data") or body.get("voices") or [])
    return [s for s in lijst if isinstance(s, dict)]


async def _laad_stemmen(sleutel: str) -> List[dict]:
    """All voices of the account. The list is paginated: on 9 October 2026 only
    the first page came back (ten English voices), so Arabic and Dutch, which
    Voxtral does have, were read with an English voice. Keep asking for the
    next page until one brings nothing new; that also stops when the server
    ignores the page parameter and keeps sending the first page."""
    global _stemmen
    if _stemmen is None:
        gevonden: List[dict] = []
        gezien: set = set()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                for pagina in range(STEMMEN_MAX_PAGINAS):
                    r = await client.get(STEMMEN_URL, headers={"Authorization": f"Bearer {sleutel}"},
                                         params={"page": pagina, "page_size": STEMMEN_PAGINA, "limit": STEMMEN_PAGINA})
                    if r.status_code != 200:
                        break
                    nieuw = [s for s in _stemmen_uit(r.json()) if _stem_id(s) and _stem_id(s) not in gezien]
                    if not nieuw:
                        break
                    gezien.update(_stem_id(s) for s in nieuw)
                    gevonden += nieuw
        except Exception:
            pass
        _stemmen = gevonden
        # Names and languages of the voices (no patient data), to see which languages have one.
        logger.info("tolk.stemmen", aantal=len(_stemmen),
                    stemmen=[f"{_stem_id(s)}:{'/'.join(_stem_talen(s))}" for s in _stemmen][:40])
    return _stemmen


# Voices the practice recorded itself, per language code (also kept in the register).
_eigen: Dict[str, str] = {}


async def eigen_stem(code: str) -> Optional[str]:
    env = os.getenv("TOLK_STEM_" + code.upper().replace("-", "_"))
    if env:
        return env
    if code in _eigen:
        return _eigen[code]
    from . import register
    if register.actief():
        try:
            rij = await register.fetchrow("SELECT waarde FROM vs_instellingen WHERE sleutel = $1", f"tolk_stem:{code}")
            if rij:
                _eigen[code] = rij["waarde"]
                return rij["waarde"]
        except Exception as exc:
            logger.warning("tolk.eigen_stem_fout", error=type(exc).__name__)
    return None


async def mistral_stem(taal: Taal) -> Optional[str]:
    """A voice of this language: recorded by the practice (exact code, e.g.
    ar-MA, then the base language), or a Mistral voice of the language."""
    sleutel = get_config().llm.mistral_api_key
    if not (sleutel and taal.tts):
        return None
    for code in dict.fromkeys([taal.code, taal.tts]):
        eigen = await eigen_stem(code)
        if eigen:
            return eigen
    return kies_stem(await _laad_stemmen(sleutel), taal.tts)


async def mistral_overig(taal: Taal) -> Optional[str]:
    """Any Mistral voice (TOLK_STEM, else the first): a foreign accent, as a last server option."""
    sleutel = get_config().llm.mistral_api_key
    if not (sleutel and taal.tts):
        return None
    if os.getenv("TOLK_STEM"):
        return os.getenv("TOLK_STEM")
    stemmen = await _laad_stemmen(sleutel)
    return _stem_id(stemmen[0]) if stemmen else None


async def stem_bron(taal: Taal) -> str:
    """Who reads this language aloud: azure, mistral or computer."""
    for bron in voorkeur():
        if bron == "azure" and azure_mag() and azure_stem(taal.code):
            return "azure"
        if bron == "mistral" and await mistral_stem(taal):
            return "mistral"
        if bron == "mistral_overig" and await mistral_overig(taal):
            return "mistral"
    return "computer"


def _audio_uit(r: httpx.Response) -> Optional[bytes]:
    soort = r.headers.get("content-type", "")
    if soort.startswith("audio/"):
        return r.content
    try:
        body = r.json()
    except ValueError:
        return None
    data = body.get("audio_data") or body.get("audio") or body.get("data")
    if isinstance(data, str):
        try:
            return base64.b64decode(data)
        except ValueError:
            return None
    return None


def _xml(tekst: str) -> str:
    return (tekst.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


async def _azure(tekst: str, taal: Taal, geslacht: str) -> Optional[bytes]:
    stem = azure_stem(taal.code, geslacht)
    regio = os.getenv("TOLK_AZURE_REGION", "westeurope")
    locale = "-".join(stem.split("-")[:2])
    tempo = os.getenv("TOLK_TEMPO", "-8%")   # a little slower: a second language, often older patients
    ssml = (f"<speak version='1.0' xml:lang='{locale}' xmlns='http://www.w3.org/2001/10/synthesis'>"
            f"<voice name='{stem}'><prosody rate='{tempo}'>{_xml(tekst)}</prosody></voice></speak>")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"https://{regio}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={"Ocp-Apim-Subscription-Key": os.getenv("TOLK_AZURE_KEY", ""),
                     "Content-Type": "application/ssml+xml",
                     "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                     "User-Agent": "VitaScribe"},
            content=ssml.encode("utf-8"),
        )
    if r.status_code == 200 and r.content:
        return r.content
    logger.warning("tolk.azure_fout", status=r.status_code, body=r.text[:200], stem=stem)
    return None


async def _mistral(tekst: str, taal: Taal, overig: bool = False) -> Optional[bytes]:
    sleutel = get_config().llm.mistral_api_key
    stem = await (mistral_overig(taal) if overig else mistral_stem(taal))
    if not stem:
        return None
    model = os.getenv("TOLK_TTS_MODEL", "voxtral-mini-tts-latest")
    basis = {"model": model, "input": tekst, "response_format": "mp3"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        # The voice field is called voice_id in Mistral's SDK and voice in the
        # OpenAI-style API; try both before giving up.
        for body in (dict(basis, voice_id=stem), dict(basis, voice=stem)):
            r = await client.post(os.getenv("TOLK_TTS_URL", TTS_URL), json=body,
                                  headers={"Authorization": f"Bearer {sleutel}"})
            if r.status_code == 200:
                audio = _audio_uit(r)
                if audio:
                    return audio
            logger.warning("tolk.tts_fout", status=r.status_code, body=r.text[:200])
    return None


async def tekst_naar_spraak(tekst: str, taal: Taal, geslacht: str = "vrouw") -> Optional[bytes]:
    """MP3 from a native voice, or None (the extension then reads aloud itself). Replaceable in tests."""
    for bron in voorkeur():
        if bron == "azure" and azure_mag() and azure_stem(taal.code):
            audio = await _azure(tekst, taal, geslacht)
        elif bron in ("mistral", "mistral_overig"):
            audio = await _mistral(tekst, taal, overig=bron == "mistral_overig")
        else:
            continue
        if audio:
            # Voices are billed per character: the cost check counts these (no text, only the length).
            logger.info("tts.usage", provider="azure" if bron == "azure" else "mistral", tekens=len(tekst), taal=taal.code)
            from . import kosten
            kosten.tel("azure_tts" if bron == "azure" else "mistral_tts", "", "stem", tekens=len(tekst))
            return audio
    return None


class SpreekRequest(BaseModel):
    tekst: str = Field(..., min_length=1, max_length=MAX_SPREEK_CHARS)
    taal: str
    geslacht: str = Field(default="vrouw", pattern="^(vrouw|man)$")


@router.post("/spreek")
async def spreek(body: SpreekRequest, user: str = Depends(verify_api_key)):
    taal = TALEN.get(body.taal)
    if not taal:
        raise HTTPException(status_code=400, detail="Onbekende taal.")
    try:
        audio = await tekst_naar_spraak(body.tekst.strip(), taal, body.geslacht)
    except Exception as exc:
        logger.warning("tolk.tts_fout", error=type(exc).__name__)
        audio = None
    if not audio:
        # Not an error for the doctor: the extension then uses a voice on the computer.
        raise HTTPException(status_code=404, detail="Geen stem op de server voor deze taal.")
    audit.log_event(user, "tolk.spreek", taal=taal.code, chars=len(body.tekst))
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


# ── 3b Own voice per language (voice cloning by Voxtral) ──

MAX_STEM_MB = 5


@router.post("/stem")
async def nieuwe_stem(
    audio: UploadFile = File(...),
    taal: str = Form(...),
    toestemming: bool = Form(default=False),
    user: str = Depends(verify_api_key),
):
    """A colleague who speaks the language natively reads 10 to 20 seconds; Mistral
    makes a voice of it, and the interpreter reads that language with it from then on.
    Never a patient: the speaker gives consent for the recording and its use."""
    t = TALEN.get(taal)
    if not t or not t.tts:
        raise HTTPException(status_code=400, detail="Voor deze taal kan Mistral geen stem maken.")
    if not toestemming:
        raise HTTPException(status_code=400, detail="De spreker moet toestemming geven voor de opname en het gebruik van de stem.")
    sleutel = get_config().llm.mistral_api_key
    if not sleutel:
        raise HTTPException(status_code=503, detail="Op de server is geen Mistral-sleutel ingesteld.")
    inhoud = await audio.read()
    if not inhoud or len(inhoud) > MAX_STEM_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="De opname is leeg of te groot.")
    body = {"name": f"VitaScribe {t.naam}", "sample_audio": base64.b64encode(inhoud).decode(),
            "sample_filename": audio.filename or "stem.webm"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(os.getenv("TOLK_STEMMEN_URL", STEMMEN_URL), json=body,
                              headers={"Authorization": f"Bearer {sleutel}"})
    if r.status_code not in (200, 201):
        logger.warning("tolk.stem_fout", status=r.status_code, body=r.text[:300])
        raise HTTPException(status_code=502, detail="Mistral kon geen stem maken van deze opname. Probeer een langere, rustige opname.")
    stem_id = _stem_id(r.json() if r.content else {})
    if not stem_id:
        raise HTTPException(status_code=502, detail="Mistral gaf geen stem terug.")
    _eigen[t.code] = stem_id
    from . import register
    if register.actief():
        await register.execute(
            "INSERT INTO vs_instellingen (sleutel, waarde) VALUES ($1, $2) "
            "ON CONFLICT (sleutel) DO UPDATE SET waarde = EXCLUDED.waarde", f"tolk_stem:{t.code}", stem_id)
    logger.info("tolk.stem_gemaakt", taal=t.code, bytes=len(inhoud))
    audit.log_event(user, "tolk.stem", taal=t.code)
    return {"taal": t.code, "stem": stem_id}


# ── 4 Verslag ──

class Beurt(BaseModel):
    spreker: str = Field(..., pattern="^(arts|patient)$")
    nl: str = Field(..., max_length=MAX_ZIN_CHARS)


class VerslagRequest(BaseModel):
    taal: str
    beurten: List[Beurt] = Field(..., min_length=1, max_length=MAX_BEURTEN)
    consent: bool = False


def gesprek_tekst(beurten: List[Beurt]) -> str:
    """De Nederlandse kant van het gesprek; opeenvolgende beurten van dezelfde
    spreker worden één alinea."""
    regels: List[List[str]] = []
    vorige = None
    for b in beurten:
        tekst = b.nl.strip()
        if not tekst:
            continue
        if b.spreker != vorige:
            regels.append(["Arts:" if b.spreker == "arts" else "Patiënt (vertaald):"])
            vorige = b.spreker
        regels[-1].append(tekst)
    return "\n".join(" ".join(r) for r in regels)


def taalregel(taal: Taal) -> str:
    return (f"CONSULT VIA DE VITASCRIBE-TOLK: de patiënt sprak {taal.naam}, de arts Nederlands. Wat bij "
            "\"Patiënt (vertaald)\" staat, is een machinevertaling van wat de patiënt zei. Schrijf de SOEP in "
            f"het Nederlands en noem in S dat het consult in het {taal.naam} ging, via een AI-tolk.\n\n")


@router.post("/verslag")
async def verslag(body: VerslagRequest, user: str = Depends(verify_api_key)):
    from .pipeline import verwerk_transcript
    _toestemming(body.consent, user)
    taal = kies(body.taal)
    tekst = gesprek_tekst(body.beurten)
    transcript = stt_service.TranscriptResult(raw_text=tekst, segments=[], language="nl",
                                              provider="tolk")
    begin = time.time()
    result = await verwerk_transcript(transcript, taalregel=taalregel(taal))
    logger.info("tolk.verslag", beurten=len(body.beurten), chars=len(tekst), taal=taal.code,
                seconden=round(time.time() - begin, 1))
    audit.log_event(user, "tolk.verslag", taal=taal.code, chars=len(tekst),
                    provider=data_policy.phi_llm_provider())
    uit = result.to_dict()
    uit["processing_time_secs"] = round(time.time() - begin, 2)
    return uit
