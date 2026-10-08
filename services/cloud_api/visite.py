"""
VitaScribe Cloud API - Visite

Visites bij patiënten thuis: opnemen op de telefoon, terug in de praktijk het
verslag in het zijpaneel, en invoegen in het dossier.

Hoe het werkt:
1. Koppelen, eenmalig. De extensie maakt een sleutelpaar (RSA-OAEP 2048). De
   geheime sleutel blijft in de browser van de praktijk en kan er niet uit;
   de openbare sleutel staat hier als "ontvanger" van de arts. Daarna toont
   het paneel een QR-code: de telefoon krijgt een eigen toestelsleutel.
2. Die toestelsleutel kan alleen schrijven: een visite insturen. Hij kan geen
   verslag lezen, geen lijst zien en niets anders. Een verloren telefoon
   levert dus niets op; intrekken kan in het paneel. Hier staat alleen de
   SHA-256 ervan.
3. De visite. De telefoon stuurt na Stop de opname met toestemming en een
   korte aanduiding. De server maakt het verslag zoals bij een consult, in de
   modus van het moment van koppelen (de EU-modus blijft de EU-modus), en
   gooit de opname meteen weg.
4. De postbus. Het verslag en de aanduiding worden meteen versleuteld voor
   elke ontvanger van de arts (AES-256-GCM, de sleutel daarvan met RSA-OAEP
   ingepakt). Daarna kan deze server ze zelf niet meer lezen. Een envelop
   wordt gewist als de arts hem weghaalt, en anders na 48 uur.

Staat standaard uit: VISITE=true zet het aan. Met het register (DATABASE_URL)
overleven de enveloppen een herstart; zonder register staan ze in het
geheugen van dit proces.

Endpoints, paneel (API-sleutel):
  POST   /api/v1/visite/ontvanger      {kid, spki}   openbare sleutel van deze browser
  POST   /api/v1/visite/koppel         {naam?}       -> {pad}: QR voor de telefoon
  DELETE /api/v1/visite/koppel                       alle telefoons van deze arts ontkoppelen
  GET    /api/v1/visite/postbus                      -> visites (aanduiding versleuteld)
  GET    /api/v1/visite/postbus/{id}                 -> envelop met het verslag
  DELETE /api/v1/visite/postbus/{id}                 weg
Endpoints, telefoon (toestelsleutel in X-VitaScribe-Visite):
  POST /api/v1/visite/hallo     -> modus en naam van de arts, om te tonen
  POST /api/v1/visite/opname    multipart: audio, toestemming, aanduiding?, taal?,
                                nadictaat_vanaf?, opgenomen?, fotos (0-6 afbeeldingen)

Deel 2: de telefoon bewaart een opname zonder bereik versleuteld en stuurt hem
later (opgenomen = het moment van opnemen); nadicteren markeert het moment
waarop de arts na het gesprek dicteert; foto's (wond, huid, medicijnlijst)
gaan mee in dezelfde envelop en verschijnen in het zijpaneel bij de visite.
Pagina: GET /v (en /v/visite.js)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import audit, data_policy, leren, register
from .auth import huidige_identiteit

logger = structlog.get_logger()
router = APIRouter(tags=["visite"])

STATIC = Path(__file__).parent / "static"
KOP = "X-VitaScribe-Visite"
BEWAAR = 48 * 3600                 # een envelop wordt uiterlijk na 48 uur gewist
TOESTEL_STIL = 60 * 24 * 3600      # een telefoon die 60 dagen niets instuurde, vervalt
MAX_TOESTELLEN = 3
MAX_ONTVANGERS = 5                 # browsers (pc's) van dezelfde arts
MAX_OPEN = 30                      # visites tegelijk in de postbus van een arts
MAX_AANDUIDING = 60
MAX_MB = 60
MAX_FOTOS = 6
MAX_FOTO_MB = 8
FOTO_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


def aan() -> bool:
    return (os.getenv("VISITE") or "false").strip().lower() == "true"


def _vereis_aan() -> None:
    if not aan():
        raise HTTPException(status_code=404, detail="Visites staan uit op deze server (VISITE=true zet ze aan).")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── Versleuteling: alleen de browser van de praktijk kan openen ──

def _laad_spki(spki_b64: str):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    sleutel = load_der_public_key(base64.b64decode(spki_b64))
    if not isinstance(sleutel, rsa.RSAPublicKey) or sleutel.key_size < 2048:
        raise ValueError("geen RSA-sleutel van 2048 bits of meer")
    return sleutel


def versleutel(gegevens: Any, ontvangers: List[Dict[str, str]]) -> Dict[str, Any]:
    """An envelope only the receivers can open: AES-256-GCM for the content,
    the AES key wrapped with RSA-OAEP-SHA-256 for each receiver (WebCrypto can
    unwrap and decrypt exactly this)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not ontvangers:
        raise ValueError("geen ontvanger")
    sleutel = AESGCM.generate_key(bit_length=256)
    iv = secrets.token_bytes(12)
    data = AESGCM(sleutel).encrypt(iv, json.dumps(gegevens, ensure_ascii=False).encode("utf-8"), None)
    oaep = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    ingepakt = {o["kid"]: base64.b64encode(_laad_spki(o["spki"]).encrypt(sleutel, oaep)).decode() for o in ontvangers}
    return {"v": 1, "alg": "RSA-OAEP-256+A256GCM", "iv": base64.b64encode(iv).decode(),
            "data": base64.b64encode(data).decode(), "sleutels": ingepakt}


# ── Opslag ──

@dataclass
class _Geheugen:
    """Without a register: in memory (lost on a restart)."""
    ontvangers: Dict[str, Dict[str, Dict]] = field(default_factory=dict)    # label -> kid -> rij
    toestellen: Dict[str, Dict] = field(default_factory=dict)               # hash -> rij
    post: Dict[str, Dict] = field(default_factory=dict)                     # id -> rij

    async def zet_ontvanger(self, wie: str, kid: str, spki: str) -> None:
        eigen = self.ontvangers.setdefault(wie, {})
        eigen[kid] = {"kid": kid, "spki": spki, "gezien": time.time()}
        for oud in sorted(eigen.values(), key=lambda r: r["gezien"])[:max(0, len(eigen) - MAX_ONTVANGERS)]:
            eigen.pop(oud["kid"], None)

    async def ontvangers_van(self, wie: str) -> List[Dict]:
        return [{"kid": r["kid"], "spki": r["spki"]} for r in self.ontvangers.get(wie, {}).values()]

    async def zet_toestel(self, h: str, wie: str, eigenaar: str, modus: str, naam: str) -> None:
        eigen = sorted((r for r in self.toestellen.values() if r["wie"] == wie), key=lambda r: r["laatst"])
        for oud in eigen[:max(0, len(eigen) - MAX_TOESTELLEN + 1)]:
            self.toestellen.pop(oud["hash"], None)
        self.toestellen[h] = {"hash": h, "wie": wie, "eigenaar": eigenaar, "modus": modus, "naam": naam,
                              "laatst": time.time()}

    async def toestel(self, h: str) -> Optional[Dict]:
        r = self.toestellen.get(h)
        if r and time.time() - r["laatst"] > TOESTEL_STIL:
            self.toestellen.pop(h, None)
            return None
        if r:
            r["laatst"] = time.time()
        return dict(r) if r else None

    async def wis_toestellen(self, wie: str) -> int:
        weg = [h for h, r in self.toestellen.items() if r["wie"] == wie]
        for h in weg:
            self.toestellen.pop(h, None)
        return len(weg)

    async def zet_post(self, rij: Dict) -> None:
        self.post[rij["id"]] = rij

    async def werk_post_bij(self, pid: str, **velden: Any) -> None:
        if pid in self.post:
            self.post[pid].update(velden)

    async def post_van(self, wie: str) -> List[Dict]:
        nu = time.time()
        return sorted((dict(r) for r in self.post.values() if r["wie"] == wie and r["verloopt"] > nu),
                      key=lambda r: r["gemaakt"])

    async def een_post(self, wie: str, pid: str) -> Optional[Dict]:
        r = self.post.get(pid)
        return dict(r) if r and r["wie"] == wie and r["verloopt"] > time.time() else None

    async def wis_post(self, wie: str, pid: str) -> bool:
        r = self.post.get(pid)
        if r and r["wie"] == wie:
            self.post.pop(pid, None)
            return True
        return False

    async def opruimen(self) -> int:
        nu = time.time()
        weg = [pid for pid, r in self.post.items() if r["verloopt"] <= nu]
        for pid in weg:
            self.post.pop(pid, None)
        return len(weg)


class _Register:
    async def zet_ontvanger(self, wie: str, kid: str, spki: str) -> None:
        await register.execute(
            """INSERT INTO vs_visite_ontvanger (wie, kid, spki) VALUES ($1, $2, $3)
               ON CONFLICT (wie, kid) DO UPDATE SET gezien = now()""", wie, kid, spki)
        await register.execute(
            """DELETE FROM vs_visite_ontvanger WHERE wie = $1 AND kid NOT IN
               (SELECT kid FROM vs_visite_ontvanger WHERE wie = $1 ORDER BY gezien DESC LIMIT $2)""",
            wie, MAX_ONTVANGERS)

    async def ontvangers_van(self, wie: str) -> List[Dict]:
        return [dict(r) for r in await register.fetch("SELECT kid, spki FROM vs_visite_ontvanger WHERE wie = $1", wie)]

    async def zet_toestel(self, h: str, wie: str, eigenaar: str, modus: str, naam: str) -> None:
        await register.execute(
            """DELETE FROM vs_visite_toestel WHERE wie = $1 AND hash NOT IN
               (SELECT hash FROM vs_visite_toestel WHERE wie = $1 ORDER BY laatst DESC LIMIT $2)""",
            wie, MAX_TOESTELLEN - 1)
        await register.execute(
            """INSERT INTO vs_visite_toestel (hash, wie, eigenaar, modus, naam) VALUES ($1, $2, $3, $4, $5)""",
            h, wie, eigenaar, modus, naam)

    async def toestel(self, h: str) -> Optional[Dict]:
        await register.execute("DELETE FROM vs_visite_toestel WHERE laatst < now() - make_interval(secs => $1)",
                               float(TOESTEL_STIL))
        r = await register.fetchrow(
            """UPDATE vs_visite_toestel SET laatst = now() WHERE hash = $1
               RETURNING hash, wie, eigenaar, modus, naam""", h)
        return dict(r) if r else None

    async def wis_toestellen(self, wie: str) -> int:
        uit = await register.execute("DELETE FROM vs_visite_toestel WHERE wie = $1", wie)
        return int(uit.split()[-1]) if uit else 0

    async def zet_post(self, rij: Dict) -> None:
        await register.execute(
            """INSERT INTO vs_visite_post (id, wie, gemaakt, verloopt, status, kop, envelop, fout)
               VALUES ($1, $2, to_timestamp($3), to_timestamp($4), $5, $6::jsonb, $7::jsonb, $8)""",
            rij["id"], rij["wie"], rij["gemaakt"], rij["verloopt"], rij["status"],
            json.dumps(rij.get("kop")), json.dumps(rij.get("envelop")), rij.get("fout", ""))

    async def werk_post_bij(self, pid: str, **velden: Any) -> None:
        await register.execute(
            """UPDATE vs_visite_post SET status = COALESCE($2, status), envelop = COALESCE($3::jsonb, envelop),
               fout = COALESCE($4, fout) WHERE id = $1""",
            pid, velden.get("status"), json.dumps(velden["envelop"]) if "envelop" in velden else None,
            velden.get("fout"))

    @staticmethod
    def _rij(r) -> Dict:
        d = dict(r)
        d["gemaakt"] = d["gemaakt"].timestamp()
        d["verloopt"] = d["verloopt"].timestamp()
        for k in ("kop", "envelop"):
            if isinstance(d.get(k), str):
                d[k] = json.loads(d[k])
        return d

    async def post_van(self, wie: str) -> List[Dict]:
        rijen = await register.fetch(
            """SELECT id, wie, gemaakt, verloopt, status, kop, NULL::jsonb AS envelop, fout FROM vs_visite_post
               WHERE wie = $1 AND verloopt > now() ORDER BY gemaakt""", wie)
        return [self._rij(r) for r in rijen]

    async def een_post(self, wie: str, pid: str) -> Optional[Dict]:
        r = await register.fetchrow(
            """SELECT id, wie, gemaakt, verloopt, status, kop, envelop, fout FROM vs_visite_post
               WHERE id = $1 AND wie = $2 AND verloopt > now()""", pid, wie)
        return self._rij(r) if r else None

    async def wis_post(self, wie: str, pid: str) -> bool:
        uit = await register.execute("DELETE FROM vs_visite_post WHERE id = $1 AND wie = $2", pid, wie)
        return not uit.endswith(" 0")

    async def opruimen(self) -> int:
        uit = await register.execute("DELETE FROM vs_visite_post WHERE verloopt <= now()")
        return int(uit.split()[-1]) if uit else 0


_geheugen = _Geheugen()


def opslag():
    return _Register() if register.actief() else _geheugen


# ── Paneel ──

class OntvangerRequest(BaseModel):
    kid: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    spki: str = Field(..., min_length=200, max_length=2000)


@router.post("/api/v1/visite/ontvanger")
async def ontvanger(body: OntvangerRequest, ident=Depends(huidige_identiteit)):
    """The public key of this browser: visit reports are encrypted for it."""
    _vereis_aan()
    try:
        _laad_spki(body.spki)
    except Exception:
        raise HTTPException(status_code=400, detail="Ongeldige openbare sleutel.")
    await opslag().zet_ontvanger(ident.label, body.kid, body.spki)
    return {"ok": True}


class KoppelRequest(BaseModel):
    naam: str = Field("", max_length=40)


@router.post("/api/v1/visite/koppel")
async def koppel(body: KoppelRequest, ident=Depends(huidige_identiteit)):
    """A write-only key for the phone, in a QR code (after '#': never sent to a server)."""
    _vereis_aan()
    if not await opslag().ontvangers_van(ident.label):
        raise HTTPException(status_code=409, detail="Deze browser heeft nog geen sleutel aangemeld. Werk de extensie bij.")
    token = secrets.token_urlsafe(32)
    await opslag().zet_toestel(_hash(token), ident.label, leren.eigenaar(), data_policy.modus(), body.naam.strip())
    audit.log_event(ident.label, "visite.koppel", mode=data_policy.modus())
    logger.info("visite.koppel", modus=data_policy.modus())
    return {"pad": "/v#" + token, "modus": data_policy.modus()}


@router.delete("/api/v1/visite/koppel")
async def ontkoppel(ident=Depends(huidige_identiteit)):
    _vereis_aan()
    weg = await opslag().wis_toestellen(ident.label)
    audit.log_event(ident.label, "visite.ontkoppel", status=str(weg))
    return {"ontkoppeld": weg}


@router.get("/api/v1/visite/postbus")
async def postbus(ident=Depends(huidige_identiteit)):
    """The visits waiting for this doctor. The label stays encrypted: the panel opens it."""
    _vereis_aan()
    await opslag().opruimen()
    return {"visites": [{"id": r["id"], "gemaakt": r["gemaakt"], "verloopt": r["verloopt"], "status": r["status"],
                         "kop": r.get("kop"), "fout": r.get("fout") or ""}
                        for r in await opslag().post_van(ident.label)]}


@router.get("/api/v1/visite/postbus/{pid}")
async def postbus_een(pid: str, ident=Depends(huidige_identiteit)):
    _vereis_aan()
    r = await opslag().een_post(ident.label, pid)
    if not r:
        raise HTTPException(status_code=404, detail="Deze visite is er niet meer (gewist of na 48 uur verlopen).")
    if r["status"] != "klaar":
        raise HTTPException(status_code=409, detail="Het verslag van deze visite is nog niet klaar.")
    audit.log_event(ident.label, "visite.open")
    return {"id": r["id"], "envelop": r["envelop"]}


@router.delete("/api/v1/visite/postbus/{pid}")
async def postbus_weg(pid: str, ident=Depends(huidige_identiteit)):
    _vereis_aan()
    ok = await opslag().wis_post(ident.label, pid)
    if ok:
        audit.log_event(ident.label, "visite.weg")
    return {"ok": ok}


# ── Telefoon ──

async def _toestel(token: Optional[str]) -> Dict:
    _vereis_aan()
    r = await opslag().toestel(_hash((token or "").strip())) if token else None
    if not r:
        raise HTTPException(status_code=401, detail="Deze telefoon is niet (meer) gekoppeld. Scan de QR-code in het zijpaneel.")
    return r


@router.post("/api/v1/visite/hallo")
async def hallo(token: Optional[str] = Header(default=None, alias=KOP)):
    t = await _toestel(token)
    return {"modus": t["modus"], "naam": t.get("naam") or ""}


async def _verwerk(pid: str, t: Dict, inhoud: bytes, ext: str, taal: Optional[str],
                   nadictaat_vanaf: Optional[float] = None, fotos: Optional[List[Dict[str, str]]] = None) -> None:
    """Make the report as for a consult, encrypt it for the doctor's browsers,
    and throw the recording away. Runs after the phone got its answer."""
    from .config import get_config
    from .pipeline import process_consultation
    tok = data_policy.zet_modus(t["modus"])
    leren.zet_eigenaar(t["eigenaar"])
    pad = None
    try:
        tmp_dir = get_config().temp_dir
        os.makedirs(tmp_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=f".{ext}", delete=False) as tmp:
            tmp.write(inhoud)
            pad = Path(tmp.name)
        del inhoud
        result = await process_consultation(audio_path=pad, taal=taal, nadictaat_vanaf=nadictaat_vanaf)
        ontvangers = await opslag().ontvangers_van(t["wie"])
        inhoud_envelop = result.to_dict()
        if fotos:
            inhoud_envelop["fotos"] = fotos   # into the same envelope: nothing readable here
        envelop = versleutel(inhoud_envelop, ontvangers)
        await opslag().werk_post_bij(pid, status="klaar", envelop=envelop)
        logger.info("visite.klaar", modus=t["modus"], ontvangers=len(ontvangers))
    except Exception as exc:  # the phone already has its answer: the panel shows the failure
        logger.error("visite.fout", error=type(exc).__name__)
        await opslag().werk_post_bij(pid, status="fout", fout="Het verslag kon niet worden gemaakt. Dicteer de visite zelf.")
    finally:
        data_policy.herstel_modus(tok)
        if pad:
            try:
                pad.unlink(missing_ok=True)   # privacy: no audio retention
            except OSError:
                pass


@router.post("/api/v1/visite/opname")
async def opname(
    achtergrond: BackgroundTasks,
    audio: UploadFile = File(...),
    toestemming: bool = Form(default=False),
    aanduiding: str = Form(default="", max_length=MAX_AANDUIDING),
    taal: Optional[str] = Form(default=None, max_length=8),
    nadictaat_vanaf: Optional[float] = Form(default=None),
    opgenomen: Optional[float] = Form(default=None),
    fotos: List[UploadFile] = File(default=[]),
    token: Optional[str] = Header(default=None, alias=KOP),
):
    """The recording of a visit. Answers at once; the report follows in the postbus."""
    t = await _toestel(token)
    if os.getenv("REQUIRE_RECORDING_CONSENT", "true").lower() == "true" and not toestemming:
        audit.log_event(t["wie"], "visite.geweigerd", status="geen_toestemming")
        raise HTTPException(status_code=400, detail="Toestemming van de patiënt voor de opname is niet bevestigd.")
    if t["modus"] not in data_policy.server_modi():
        raise HTTPException(status_code=403, detail="Deze server staat de modus van deze koppeling niet meer toe. Koppel opnieuw.")
    inhoud = await audio.read()
    if len(inhoud) < 1000:
        raise HTTPException(status_code=400, detail="De opname is leeg of te kort.")
    if len(inhoud) > MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"De opname is te groot (maximaal {MAX_MB} MB).")
    if len(fotos) > MAX_FOTOS:
        raise HTTPException(status_code=400, detail=f"Hooguit {MAX_FOTOS} foto's per visite.")
    beelden: List[Dict[str, str]] = []
    for f in fotos:
        soort = (f.content_type or "").lower()
        data = await f.read()
        if soort not in FOTO_TYPES or not data:
            raise HTTPException(status_code=400, detail="Een foto heeft een onbekend formaat (jpg, png, heic).")
        if len(data) > MAX_FOTO_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Een foto is te groot (maximaal {MAX_FOTO_MB} MB).")
        beelden.append({"media_type": soort, "data": base64.b64encode(data).decode()})
    open_ = await opslag().post_van(t["wie"])
    if len(open_) >= MAX_OPEN:
        raise HTTPException(status_code=429, detail="Er staan al veel visites klaar. Verwerk ze eerst in het zijpaneel.")
    ontvangers = await opslag().ontvangers_van(t["wie"])
    if not ontvangers:
        raise HTTPException(status_code=409, detail="Er is geen browser om het verslag voor te versleutelen. Koppel opnieuw.")
    nu = time.time()
    pid = str(uuid.uuid4())
    # Sent later (no signal at the visit): the moment of recording, within the 48 hours.
    moment = min(nu, max(nu - BEWAAR, float(opgenomen))) if opgenomen else nu
    # The label is encrypted at once as well: nothing readable stays here.
    kop = versleutel({"aanduiding": aanduiding.strip()[:MAX_AANDUIDING], "gemaakt": moment,
                      "fotos": len(beelden)}, ontvangers)
    await opslag().zet_post({"id": pid, "wie": t["wie"], "gemaakt": moment, "verloopt": moment + BEWAAR,
                             "status": "verwerken", "kop": kop, "envelop": None, "fout": ""})
    ext = (Path(audio.filename or "").suffix.lstrip(".").lower() or "webm")[:5]
    vanaf = nadictaat_vanaf if nadictaat_vanaf is not None and nadictaat_vanaf >= 0 else None
    achtergrond.add_task(_verwerk, pid, t, inhoud, ext, taal, vanaf, beelden)
    audit.log_event(t["wie"], "visite.opname", consent=True, mode=t["modus"], status=f"fotos={len(beelden)}")
    return {"id": pid, "status": "verwerken"}


def _bestand(naam: str, soort: Optional[str] = None) -> FileResponse:
    return FileResponse(STATIC / naam, media_type=soort, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'self'; media-src 'self' blob:; img-src 'self' data: blob:; "
                                   "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"})


@router.get("/v", include_in_schema=False)
async def visitepagina():
    return _bestand("visite.html", "text/html; charset=utf-8")


@router.get("/v/visite.js", include_in_schema=False)
async def visite_js():
    return _bestand("visite.js", "application/javascript")
