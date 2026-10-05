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

Welke talen kunnen, hangt af van de modus. In de EU-modus verstaat alleen
Voxtral (Mistral, EU) de spraak, en Voxtral kent geen Turks, Pools of
Oekraïens. In de Claude-modus verstaat Deepgram (EU-eindpunt) alle talen
hieronder, ook Marokkaans- en Syrisch-Arabisch als eigen dialect.

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
import time
from typing import Dict, List, NamedTuple, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

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
    deepgram: str             # Deepgram "language"
    voxtral: Optional[str]    # Voxtral Transcribe; None = verstaat Voxtral niet
    tts: Optional[str]        # Voxtral TTS; None = alleen een stem op de computer
    prompt: str               # hoe het taalmodel de taal moet schrijven


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
]}
ARTS_TAAL = TALEN["nl"]


def kies(code: Optional[str]) -> Taal:
    taal = TALEN.get(str(code or "").strip())
    if not taal or taal.code == "nl":
        raise HTTPException(status_code=400, detail="Kies de taal van de patiënt.")
    return taal


def verstaat(taal: Taal) -> bool:
    """Kan de spraakherkenning van deze modus deze taal verstaan?"""
    return taal.voxtral is not None if data_policy.eu_modus() else True


def mistral_stem_kan(taal: Taal) -> bool:
    return bool(taal.tts and get_config().llm.mistral_api_key)


def talen_overzicht() -> List[dict]:
    uit = []
    for t in TALEN.values():
        if t.code == "nl":
            continue
        uit.append({
            "code": t.code, "naam": t.naam, "eigen": t.eigen,
            "verstaat": verstaat(t),
            "stem": "mistral" if mistral_stem_kan(t) else "computer",
            "waarom": "" if verstaat(t) else
                      f"In de EU-modus verstaat de spraakherkenning (Voxtral, Mistral) geen {t.naam}.",
        })
    return uit


@router.get("/talen")
async def talen(_user: str = Depends(verify_api_key)):
    return {"modus": data_policy.modus(), "talen": talen_overzicht(),
            "nl_stem": "mistral" if mistral_stem_kan(ARTS_TAAL) else "computer"}


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
    kanalen = (r.json().get("results") or {}).get("channels") or [{}]
    alts = kanalen[0].get("alternatives") or [{}]
    return str(alts[0].get("transcript") or "").strip()


async def spraak_naar_tekst(audio: bytes, taal: Taal, deepgram_sleutel: Optional[str],
                            content_type: str = "audio/webm") -> str:
    """Vervangbaar in tests."""
    if data_policy.eu_modus():
        res = await stt_service._transcribe_voxtral(audio, taal.voxtral, naam="beurt.webm", diarize=False)
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
                    eenvoudiger: bool = False) -> "tuple[str, str]":
    bron, doel = (ARTS_TAAL, taal) if spreker == "arts" else (taal, ARTS_TAAL)
    system = VERTAAL_SYSTEM.format(bron=bron.prompt, doel=doel.prompt,
                                   eenvoudiger=EENVOUDIGER if eenvoudiger else "")
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
    system, user = vertaal_prompts(tekst, spreker, taal, eerder, eenvoudiger)
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
    spreker: str = Form(..., pattern="^(arts|patient)$"),
    taal: str = Form(...),
    consent: bool = Form(default=False),
    eerder: Optional[str] = Form(default=None),
    eenvoudiger: bool = Form(default=False),
    ident=Depends(huidige_identiteit),
):
    """Eén beurt: verstaan (of de tekst van een eerdere beurt opnieuw) en vertalen."""
    user = ident.label
    _toestemming(consent, user)
    patient = kies(taal)
    bron = ARTS_TAAL if spreker == "arts" else patient
    begin = time.time()
    if tekst and tekst.strip():
        # "Zeg het eenvoudiger": the text is already there, no audio again.
        origineel = tekst.strip()
        grootte = 0
    else:
        if audio is None:
            raise HTTPException(status_code=400, detail="Geen opname ontvangen.")
        if not verstaat(bron):
            raise HTTPException(status_code=400, detail=f"In de EU-modus verstaat de spraakherkenning geen {bron.naam}.")
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
        try:
            origineel = await spraak_naar_tekst(inhoud, bron, sleutel, audio.content_type or "audio/webm")
        except ValueError as exc:
            logger.warning("tolk.stt_fout", error=str(exc)[:200], taal=bron.code)
            raise HTTPException(status_code=502, detail="De spraak kon niet worden verstaan. Probeer het opnieuw.")
        except Exception as exc:
            logger.warning("tolk.stt_fout", error=type(exc).__name__, taal=bron.code)
            raise HTTPException(status_code=502, detail="De spraakherkenning reageert niet. Probeer het zo opnieuw.")
    if not origineel:
        audit.log_event(user, "tolk.beurt", spreker=spreker, taal=patient.code, status="leeg", bytes=grootte)
        return {"spreker": spreker, "origineel": "", "vertaling": "", "terugvertaling": "",
                "onzeker": False, "twijfel": "", "leeg": True}
    try:
        uit = await vertaal(origineel, spreker, patient, _eerder(eerder), eenvoudiger)
    except ValueError as exc:   # includes json.JSONDecodeError
        logger.warning("tolk.vertaal_fout", error=str(exc)[:200])
        raise HTTPException(status_code=502, detail="De vertaling lukte niet. Probeer het opnieuw.")
    except Exception as exc:
        logger.warning("tolk.vertaal_fout", error=type(exc).__name__)
        raise HTTPException(status_code=502, detail="De AI-dienst reageert niet. Probeer het zo opnieuw.")
    # Content-free: who, which language, sizes and time.
    logger.info("tolk.beurt", spreker=spreker, taal=patient.code, bytes=grootte, chars=len(origineel),
                onzeker=uit["onzeker"], seconden=round(time.time() - begin, 1), modus=data_policy.modus())
    audit.log_event(user, "tolk.beurt", spreker=spreker, taal=patient.code, chars=len(origineel),
                    provider=data_policy.phi_llm_provider())
    return {"spreker": spreker, "origineel": origineel, **uit, "leeg": False}


# ── 3 Voorlezen (Voxtral TTS, Mistral) ──

TTS_URL = "https://api.mistral.ai/v1/audio/speech"
STEMMEN_URL = "https://api.mistral.ai/v1/audio/voices"
_stemmen: Optional[List[dict]] = None


def _stem_id(stem: dict) -> str:
    for k in ("id", "voice_id", "slug", "name"):
        if stem.get(k):
            return str(stem[k])
    return ""


def kies_stem(stemmen: List[dict], taal: str) -> Optional[str]:
    """Een stem voor deze taal: eerst een die de taal noemt, dan een met de taal
    als voorvoegsel (zoals "fr_marie_neutral"), anders de eerste. Voxtral TTS
    spreekt de taal van de tekst, ook met een stem uit een andere taal."""
    eigen = os.getenv(f"TOLK_STEM_{taal.upper()}") or os.getenv("TOLK_STEM")
    if eigen:
        return eigen
    for s in stemmen:
        talen = s.get("languages") or s.get("language") or []
        talen = [talen] if isinstance(talen, str) else talen
        if any(str(t).lower().split("-")[0] == taal for t in talen):
            return _stem_id(s)
    for s in stemmen:
        if _stem_id(s).lower().startswith(taal + "_"):
            return _stem_id(s)
    return _stem_id(stemmen[0]) if stemmen else None


async def _laad_stemmen(client: httpx.AsyncClient, sleutel: str) -> List[dict]:
    global _stemmen
    if _stemmen is None:
        try:
            r = await client.get(STEMMEN_URL, headers={"Authorization": f"Bearer {sleutel}"})
            body = r.json() if r.status_code == 200 else {}
            lijst = body if isinstance(body, list) else (body.get("items") or body.get("data") or body.get("voices") or [])
            _stemmen = [s for s in lijst if isinstance(s, dict)]
        except Exception:
            _stemmen = []
        logger.info("tolk.stemmen", aantal=len(_stemmen))
    return _stemmen


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


async def tekst_naar_spraak(tekst: str, taal: Taal) -> Optional[bytes]:
    """MP3 van Voxtral TTS, of None (dan leest de extensie zelf voor). Vervangbaar in tests."""
    sleutel = get_config().llm.mistral_api_key
    if not (sleutel and taal.tts):
        return None
    model = os.getenv("TOLK_TTS_MODEL", "voxtral-mini-tts-latest")
    async with httpx.AsyncClient(timeout=60.0) as client:
        stem = kies_stem(await _laad_stemmen(client, sleutel), taal.tts)
        basis = {"model": model, "input": tekst, "response_format": "mp3"}
        # The voice field is called voice_id in Mistral's SDK and voice in the
        # OpenAI-style API; try both before giving up.
        pogingen = [dict(basis, voice_id=stem), dict(basis, voice=stem)] if stem else [basis]
        for body in pogingen:
            r = await client.post(os.getenv("TOLK_TTS_URL", TTS_URL), json=body,
                                  headers={"Authorization": f"Bearer {sleutel}"})
            if r.status_code == 200:
                audio = _audio_uit(r)
                if audio:
                    return audio
            logger.warning("tolk.tts_fout", status=r.status_code, body=r.text[:200])
    return None


class SpreekRequest(BaseModel):
    tekst: str = Field(..., min_length=1, max_length=MAX_SPREEK_CHARS)
    taal: str


@router.post("/spreek")
async def spreek(body: SpreekRequest, user: str = Depends(verify_api_key)):
    taal = TALEN.get(body.taal)
    if not taal:
        raise HTTPException(status_code=400, detail="Onbekende taal.")
    try:
        audio = await tekst_naar_spraak(body.tekst.strip(), taal)
    except Exception as exc:
        logger.warning("tolk.tts_fout", error=type(exc).__name__)
        audio = None
    if not audio:
        # Not an error for the doctor: the extension then uses a voice on the computer.
        raise HTTPException(status_code=404, detail="Geen stem op de server voor deze taal.")
    audit.log_event(user, "tolk.spreek", taal=taal.code, chars=len(body.tekst))
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


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
