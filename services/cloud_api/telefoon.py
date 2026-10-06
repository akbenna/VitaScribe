"""
VitaScribe Cloud API - Telefoon of iPad als tweede apparaat

De arts koppelt een telefoon of iPad aan het zijpaneel met een QR-code. De
telefoon opent /m op deze server (geen app, geen App Store) en werkt daarna
mee in de lopende sessie:

  tolk  de telefoon luistert handsfree (betere microfoon dan de pc) en leest
        de vertaling voor met de stemmen van het toestel zelf (iOS spreekt die
        op het apparaat, zonder cloud). Elke beurt verschijnt ook in het paneel,
        zodat "Maak verslag" gewoon werkt.
  foto  een foto (huid, wond, medicijnlijst, meegebrachte brief) gaat direct
        naar het paneel, bijvoorbeeld als schermafdruk bij een brief.

Hoe de koppeling werkt:
- het paneel vraagt met zijn API-sleutel een koppeling aan; die krijgt een
  willekeurig geheim (192 bits), de identiteit van de arts, de modus en de
  toestemming van dat moment;
- het geheim staat alleen in de QR-code en daarna in het geheugen van de
  telefoonpagina; het gaat mee als header (X-VitaScribe-Koppel), nooit in een
  adres, zodat het niet in logs belandt;
- berichten tussen paneel en telefoon staan alleen in het werkgeheugen van de
  server, tot de andere kant ze ophaalt (long-poll); een koppeling verloopt na
  twee uur zonder gebruik en na twaalf uur altijd;
- de telefoon doet alles namens de arts die koppelde, in de modus van dat
  moment: de EU-modus blijft de EU-modus. Er wordt niets bewaard.

Eén servertak: de koppelingen staan in het geheugen van dit proces. Draai de
server daarom met één replica (Railway: zo staat hij nu).

Endpoints, paneel (API-sleutel en koppelgeheim):
  POST   /api/v1/telefoon/koppel          {taal?, toestemming} -> {geheim, pad}
  POST   /api/v1/telefoon/paneel          {type, data}   bericht naar de telefoon
  GET    /api/v1/telefoon/paneel/ontvang  ?wacht=        berichten van de telefoon
  DELETE /api/v1/telefoon/koppel                         ontkoppelen
Endpoints, telefoon (alleen koppelgeheim):
  POST /api/v1/telefoon/hallo   -> taal en modus; het paneel ziet "verbonden"
  GET  /api/v1/telefoon/ontvang ?wacht=
  POST /api/v1/telefoon/status  {status}
  POST /api/v1/telefoon/beurt   multipart audio (+ spreker, eerder)
  POST /api/v1/telefoon/spreek  {tekst, taal}  stem van de server (als het toestel er geen heeft)
  POST /api/v1/telefoon/foto    multipart afbeelding
Pagina: GET /m (en /m/telefoon.js, /m/tolk.js)
"""

from __future__ import annotations

import asyncio
import base64
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import audit, data_policy, leren, tolk
from .auth import huidige_identiteit

logger = structlog.get_logger()
router = APIRouter(tags=["telefoon"])

STATIC = Path(__file__).parent / "static"
KOP = "X-VitaScribe-Koppel"
MAX_LEEFTIJD = 12 * 3600       # een koppeling geldt hooguit een werkdag
MAX_STIL = 2 * 3600            # en vervalt na twee uur zonder gebruik
MAX_WACHT = 25                 # long-poll: zo lang wacht een ophaalvraag
MAX_BERICHTEN = 40             # per kant in de wachtrij; ouder valt weg
MAX_FOTO_MB = 6
MAX_PER_ARTS = 3               # oudere koppelingen van dezelfde arts vervallen
FOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
PANEEL_TYPES = {"spreek", "stop", "taal"}
TELEFOON_STATUS = {"luistert", "hoort", "verwerkt", "spreekt", "pauze", "gestopt"}


@dataclass
class Koppeling:
    geheim: str
    ident: Any
    label: str
    modus: str
    eigenaar: str
    taal: Optional[str]
    toestemming: bool
    gemaakt: float = field(default_factory=time.time)
    laatst: float = field(default_factory=time.time)
    telefoon_gezien: bool = False
    naar_paneel: List[dict] = field(default_factory=list)
    naar_telefoon: List[dict] = field(default_factory=list)
    signaal_paneel: asyncio.Event = field(default_factory=asyncio.Event)
    signaal_telefoon: asyncio.Event = field(default_factory=asyncio.Event)


_koppelingen: Dict[str, Koppeling] = {}


def _opruimen(nu: Optional[float] = None) -> None:
    nu = nu or time.time()
    for g, k in list(_koppelingen.items()):
        if nu - k.gemaakt > MAX_LEEFTIJD or nu - k.laatst > MAX_STIL:
            _koppelingen.pop(g, None)


def _zoek(geheim: Optional[str]) -> Koppeling:
    _opruimen()
    k = _koppelingen.get((geheim or "").strip())
    if not k:
        raise HTTPException(status_code=410, detail="Deze koppeling is verlopen. Scan de QR-code in het zijpaneel opnieuw.")
    k.laatst = time.time()
    return k


def _zoek_paneel(geheim: Optional[str], ident) -> Koppeling:
    k = _zoek(geheim)
    if k.label != ident.label:
        raise HTTPException(status_code=403, detail="Deze koppeling hoort bij een andere gebruiker.")
    return k


def _stuur(k: Koppeling, naar: str, bericht: dict) -> None:
    lijst, signaal = ((k.naar_paneel, k.signaal_paneel) if naar == "paneel"
                      else (k.naar_telefoon, k.signaal_telefoon))
    lijst.append(bericht)
    del lijst[:-MAX_BERICHTEN]
    signaal.set()


async def _ontvang(k: Koppeling, kant: str, wacht: float) -> List[dict]:
    """Long-poll: what is waiting for this side, or wait for it (at most `wacht` s)."""
    lijst, signaal = ((k.naar_paneel, k.signaal_paneel) if kant == "paneel"
                      else (k.naar_telefoon, k.signaal_telefoon))
    if not lijst and wacht > 0:
        signaal.clear()
        try:
            await asyncio.wait_for(signaal.wait(), timeout=min(wacht, MAX_WACHT))
        except asyncio.TimeoutError:
            pass
    uit = list(lijst)
    lijst.clear()
    return uit


def _taalinfo(code: Optional[str]) -> Optional[dict]:
    t = tolk.TALEN.get(code or "")
    if not t or t.code == "nl":
        return None
    return {"code": t.code, "naam": t.naam, "eigen": t.eigen, "verstaat": tolk.verstaat(t)}


class _Namens:
    """Do what the phone asks as the doctor who paired it: same mode, same learning owner."""

    def __init__(self, k: Koppeling):
        self.k = k

    def __enter__(self):
        self.t_modus = data_policy.zet_modus(self.k.modus)
        leren.zet_eigenaar(self.k.eigenaar)
        return self.k

    def __exit__(self, *exc):
        data_policy.herstel_modus(self.t_modus)
        return False


# ── Paneel ──

class KoppelRequest(BaseModel):
    taal: Optional[str] = Field(default=None, max_length=10)
    toestemming: bool = False


@router.post("/api/v1/telefoon/koppel")
async def koppel(body: KoppelRequest, ident=Depends(huidige_identiteit)):
    _opruimen()
    if body.taal:
        tolk.kies(body.taal)   # 400 for an unknown language
    eigen = sorted((k for k in _koppelingen.values() if k.label == ident.label), key=lambda k: k.gemaakt)
    for oud in eigen[:max(0, len(eigen) - MAX_PER_ARTS + 1)]:
        _koppelingen.pop(oud.geheim, None)
    geheim = secrets.token_urlsafe(24)
    _koppelingen[geheim] = Koppeling(
        geheim=geheim, ident=ident, label=ident.label, modus=data_policy.modus(), eigenaar=leren.eigenaar(),
        taal=body.taal, toestemming=bool(body.toestemming),
    )
    logger.info("telefoon.koppel", modus=data_policy.modus(), tolk=bool(body.taal))
    audit.log_event(ident.label, "telefoon.koppel", mode=data_policy.modus(), status="tolk" if body.taal else "foto")
    return {"geheim": geheim, "pad": "/m#" + geheim, "verloopt_na_sec": MAX_STIL}


class PaneelBericht(BaseModel):
    type: str = Field(..., max_length=20)
    data: Dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/telefoon/paneel")
async def paneel_bericht(body: PaneelBericht, geheim: Optional[str] = Header(default=None, alias=KOP),
                         ident=Depends(huidige_identiteit)):
    k = _zoek_paneel(geheim, ident)
    if body.type not in PANEEL_TYPES:
        raise HTTPException(status_code=400, detail="Onbekend bericht.")
    if body.type == "spreek":
        tekst = str(body.data.get("tekst") or "")[:tolk.MAX_SPREEK_CHARS]
        body.data = {"tekst": tekst, "taal": str(body.data.get("taal") or "")[:10]}
    _stuur(k, "telefoon", {"type": body.type, "data": body.data})
    return {"ok": True, "telefoon": k.telefoon_gezien}


@router.get("/api/v1/telefoon/paneel/ontvang")
async def paneel_ontvang(wacht: float = 20, geheim: Optional[str] = Header(default=None, alias=KOP),
                         ident=Depends(huidige_identiteit)):
    k = _zoek_paneel(geheim, ident)
    return {"berichten": await _ontvang(k, "paneel", wacht)}


@router.delete("/api/v1/telefoon/koppel")
async def ontkoppel(geheim: Optional[str] = Header(default=None, alias=KOP), ident=Depends(huidige_identiteit)):
    k = _koppelingen.get((geheim or "").strip())
    if k and k.label == ident.label:
        _stuur(k, "telefoon", {"type": "stop", "data": {"reden": "ontkoppeld"}})
        # Give the phone one poll to hear it, then forget the pairing.
        k.toestemming = False
        k.gemaakt = time.time() - MAX_LEEFTIJD + 30
    return {"ok": True}


# ── Telefoon ──

@router.post("/api/v1/telefoon/hallo")
async def hallo(geheim: Optional[str] = Header(default=None, alias=KOP)):
    k = _zoek(geheim)
    eerste = not k.telefoon_gezien
    k.telefoon_gezien = True
    with _Namens(k):
        taal = _taalinfo(k.taal)
    _stuur(k, "paneel", {"type": "verbonden", "data": {"eerste": eerste}})
    return {"taal": taal, "modus": k.modus, "toestemming": k.toestemming, "rtl": bool(taal and taal["code"].startswith("ar"))}


@router.get("/api/v1/telefoon/ontvang")
async def telefoon_ontvang(wacht: float = 20, geheim: Optional[str] = Header(default=None, alias=KOP)):
    k = _zoek(geheim)
    return {"berichten": await _ontvang(k, "telefoon", wacht)}


class StatusRequest(BaseModel):
    status: str = Field(..., max_length=20)


@router.post("/api/v1/telefoon/status")
async def telefoon_status(body: StatusRequest, geheim: Optional[str] = Header(default=None, alias=KOP)):
    k = _zoek(geheim)
    if body.status not in TELEFOON_STATUS:
        raise HTTPException(status_code=400, detail="Onbekende status.")
    _stuur(k, "paneel", {"type": "status", "data": {"status": body.status}})
    return {"ok": True}


@router.post("/api/v1/telefoon/beurt")
async def telefoon_beurt(
    audio: UploadFile = File(...),
    spreker: str = Form(default="auto", pattern="^(arts|patient|auto)$"),
    eerder: Optional[str] = Form(default=None),
    geheim: Optional[str] = Header(default=None, alias=KOP),
):
    """A turn heard by the phone: the same as /tolk/beurt, as the doctor who paired it."""
    k = _zoek(geheim)
    if not k.taal:
        raise HTTPException(status_code=400, detail="Start het tolkgesprek in het zijpaneel.")
    with _Namens(k):
        uit = await tolk.beurt(audio=audio, tekst=None, spreker=spreker, taal=k.taal, consent=k.toestemming,
                               eerder=eerder, eenvoudiger=False, ident=k.ident)
    if not uit.get("leeg"):
        _stuur(k, "paneel", {"type": "beurt", "data": uit})
    return uit


class SpreekRequest(BaseModel):
    tekst: str = Field(..., min_length=1, max_length=tolk.MAX_SPREEK_CHARS)
    taal: str = Field(..., max_length=10)


@router.post("/api/v1/telefoon/spreek")
async def telefoon_spreek(body: SpreekRequest, geheim: Optional[str] = Header(default=None, alias=KOP)):
    k = _zoek(geheim)
    taal = tolk.TALEN.get(body.taal)
    if not taal:
        raise HTTPException(status_code=400, detail="Onbekende taal.")
    with _Namens(k):
        try:
            audio = await tolk.tekst_naar_spraak(body.tekst.strip(), taal)
        except Exception as exc:
            logger.warning("telefoon.tts_fout", error=type(exc).__name__)
            audio = None
    if not audio:
        raise HTTPException(status_code=404, detail="Geen stem op de server voor deze taal.")
    audit.log_event(k.label, "tolk.spreek", taal=taal.code, chars=len(body.tekst), mode="telefoon")
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.post("/api/v1/telefoon/foto")
async def telefoon_foto(foto: UploadFile = File(...), geheim: Optional[str] = Header(default=None, alias=KOP)):
    k = _zoek(geheim)
    soort = (foto.content_type or "").lower()
    if soort not in FOTO_TYPES:
        raise HTTPException(status_code=400, detail="Alleen een foto (JPEG, PNG, WebP of HEIC).")
    inhoud = await foto.read()
    if not inhoud:
        raise HTTPException(status_code=400, detail="Lege foto.")
    if len(inhoud) > MAX_FOTO_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Deze foto is te groot.")
    _stuur(k, "paneel", {"type": "foto", "data": {"media_type": soort, "data": base64.b64encode(inhoud).decode()}})
    logger.info("telefoon.foto", bytes=len(inhoud))
    audit.log_event(k.label, "telefoon.foto", bytes=len(inhoud))
    return {"ok": True}


# ── De pagina voor de telefoon ──

CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")


def _bestand(naam: str, soort: Optional[str] = None) -> FileResponse:
    return FileResponse(STATIC / naam, media_type=soort, headers={
        "Cache-Control": "no-cache",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": CSP,
        "Permissions-Policy": "microphone=(self), camera=(self)",
    })


@router.get("/m", include_in_schema=False)
async def telefoonpagina():
    return _bestand("telefoon.html")


@router.get("/m/telefoon.js", include_in_schema=False)
async def telefoon_js():
    return _bestand("telefoon.js", "text/javascript")


@router.get("/m/tolk.js", include_in_schema=False)
async def telefoon_tolk_js():
    return _bestand("tolk.js", "text/javascript")
