"""
VitaScribe Cloud API - Beheer van praktijken, gebruikers en licenties

  /beheer                  de beheerpagina (static/beheer.html)
  /api/v1/beheer/...       de gegevens erachter, alleen met X-Beheer-Sleutel

Beheerders staan in de omgeving:

  ADMIN_USERS  "naam:sleutel,naam2:sleutel2"  een sleutel per beheerder, zodat
               het beheerlog laat zien wie wat deed (voorkeur);
  ADMIN_KEY    één gedeelde sleutel (naam "beheerder"), voor oudere uitrol;
  ADMIN_TOTP   "naam:GEHEIM,..."  tweestapsverificatie per beheerder, met een
               base32-geheim voor een authenticator-app (RFC 6238, 30 s, 6 cijfers).

Inloggen gaat via POST /api/v1/beheer/inloggen met sleutel en, als die beheerder
een ADMIN_TOTP heeft, de code uit de app. Dat geeft een sessie van
BEHEER_SESSIE_UREN (standaard 8) uur, die de pagina meestuurt als
X-Beheer-Sessie. Een beheerder zonder ADMIN_TOTP mag ook nog rechtstreeks met
X-Beheer-Sleutel. Zonder beheerders of zonder register staat het beheer uit. Na
tien foute pogingen vanaf één adres in een kwartier weigert de server dat adres
een kwartier lang.

Werkwijze, gelijk aan Bricks Companion maar op de server:

  aanmelding  een praktijk meldt zich via /aanmelden: status 'aangemeld',
              licentietype 'kandidaat'.
  activeren   de beheerder kiest het licentietype (pilot, betaald, intern), de
              vervaldatum (pilot: standaard twaalf maanden) en de
              praktijknummers, en maakt de gebruikers aan. Elke gebruiker krijgt
              een eigen sleutel, die één keer wordt getoond.
  uithalen    status 'uitgehaald': alle sleutels van de praktijk werken binnen
              een halve minuut niet meer.

Een sleutel van een gebruiker wordt nergens bewaard, alleen de sha256 ervan.
Kwijt is kwijt: dan maakt de beheerder een nieuwe, en werkt de oude niet meer.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import audit, licentie, register

logger = structlog.get_logger()
router = APIRouter(tags=["beheer"])
STATIC = Path(__file__).parent / "static"

LICENTIETYPES = ("kandidaat", "pilot", "betaald", "intern")
STATUSSEN = ("aangemeld", "actief", "uitgehaald", "afgewezen")
ROLLEN = ("gebruiker", "praktijkbeheerder")
PILOT_MAANDEN = 12

_mislukt: Dict[str, List[float]] = {}


def _plus_maanden(d: date, maanden: int) -> date:
    jaar, maand = divmod(d.month - 1 + maanden, 12)
    jaar += d.year
    maand += 1
    import calendar
    dag = min(d.day, calendar.monthrange(jaar, maand)[1])
    return date(jaar, maand, dag)


def _adres(request: Request) -> str:
    """Het adres dat de proxy van Railway als laatste toevoegt. Het eerste deel
    van X-Forwarded-For kan de bezoeker zelf invullen."""
    kop = request.headers.get("x-forwarded-for", "")
    if kop:
        return kop.split(",")[-1].strip()
    return request.client.host if request.client else "?"


# ── Beheerders, tweestapsverificatie en sessies ──

_sessies: Dict[str, Tuple[str, float]] = {}


def _paren(waarde: str) -> Dict[str, str]:
    uit: Dict[str, str] = {}
    for deel in (waarde or "").split(","):
        if ":" in deel:
            naam, rest = deel.split(":", 1)
            if naam.strip() and rest.strip():
                uit[naam.strip()] = rest.strip()
    return uit


def beheerders() -> Dict[str, str]:
    """naam -> sleutel."""
    uit = _paren(os.getenv("ADMIN_USERS") or "")
    gedeeld = (os.getenv("ADMIN_KEY") or "").strip()
    if gedeeld:
        uit.setdefault("beheerder", gedeeld)
    return uit


def totp_geheimen() -> Dict[str, str]:
    """naam -> base32-geheim voor de authenticator-app."""
    return _paren(os.getenv("ADMIN_TOTP") or "")


def totp_code(geheim: str, moment: float) -> str:
    """De code van RFC 6238 (HMAC-SHA1, 30 seconden, 6 cijfers)."""
    sleutel = base64.b32decode(geheim.replace(" ", "").upper() + "=" * (-len(geheim.replace(" ", "")) % 8))
    teller = struct.pack(">Q", int(moment // 30))
    h = hmac.new(sleutel, teller, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    getal = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{getal:06d}"


def totp_klopt(geheim: str, code: str, moment: Optional[float] = None) -> bool:
    """Klopt de code, met een half venster speling voor een klok die iets afwijkt?"""
    code = (code or "").strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False
    nu = time.time() if moment is None else moment
    try:
        return any(hmac.compare_digest(totp_code(geheim, nu + stap * 30), code) for stap in (-1, 0, 1))
    except (ValueError, base64.binascii.Error):
        logger.error("beheer.totp_geheim_ongeldig")
        return False


def _sessie_uren() -> float:
    try:
        return max(float(os.getenv("BEHEER_SESSIE_UREN") or 8), 0.25)
    except ValueError:
        return 8.0


def _naam_bij_sleutel(sleutel: Optional[str]) -> Optional[str]:
    if not sleutel:
        return None
    for naam, verwacht in beheerders().items():
        if hmac.compare_digest(sleutel.strip(), verwacht):
            return naam
    return None


def _controleer_poort(request: Request) -> Tuple[str, List[float]]:
    if not beheerders():
        raise HTTPException(status_code=503, detail="Beheer staat uit: ADMIN_USERS of ADMIN_KEY ontbreekt op de server.")
    if not register.actief():
        raise HTTPException(status_code=503, detail="Beheer staat uit: er is geen database gekoppeld (DATABASE_URL).")
    adres = _adres(request)
    nu = time.time()
    pogingen = [t for t in _mislukt.get(adres, []) if nu - t < 900]
    _mislukt[adres] = pogingen
    alle = [t for lijst in _mislukt.values() for t in lijst]
    if len(pogingen) >= 10 or len(alle) >= 50:
        raise HTTPException(status_code=429, detail="Te veel foute pogingen. Probeer het over een kwartier opnieuw.")
    return adres, pogingen


async def vereis_beheerder(
    request: Request,
    sleutel: Optional[str] = Header(default=None, alias="X-Beheer-Sleutel"),
    sessie: Optional[str] = Header(default=None, alias="X-Beheer-Sessie"),
) -> str:
    _, pogingen = _controleer_poort(request)
    nu = time.time()
    if sessie:
        gevonden = _sessies.get(sessie.strip())
        if gevonden and gevonden[1] > nu and gevonden[0] in beheerders():
            return gevonden[0]
        _sessies.pop(sessie.strip(), None)
        raise HTTPException(status_code=401, detail="De sessie is verlopen. Log opnieuw in.")
    naam = _naam_bij_sleutel(sleutel)
    if naam is None:
        pogingen.append(nu)
        raise HTTPException(status_code=403, detail="Onjuiste beheersleutel.")
    if naam in totp_geheimen():
        raise HTTPException(status_code=401, detail="Log in met je sleutel en de code uit je authenticator-app.")
    return naam


TESTGEREEDSCHAP = "testgereedschap"


async def testgereedschap_aan() -> bool:
    """The administrator's switch in Beheer (Instellingen). The test tools
    (speech test, SOEP test, test set) send audio and text to every
    provider, in both modes, and the test-set reports write full text to the
    server log; they are meant for played consults (DPIA R7). Off until an
    administrator switches them on; without a register they stay off."""
    if not register.actief():
        return False
    try:
        rij = await register.fetchrow("SELECT waarde FROM vs_instellingen WHERE sleutel = $1", TESTGEREEDSCHAP)
    except Exception as e:      # register unreachable: the safe side
        logger.warning("beheer.testgereedschap_onleesbaar", fout=type(e).__name__)
        return False
    return bool(rij) and rij["waarde"] == "aan"


async def vereis_testgereedschap() -> None:
    """The test tools exist only while the administrator has them switched on."""
    if not await testgereedschap_aan():
        raise HTTPException(status_code=404,
                            detail="Het testgereedschap staat uit. Zet het aan in Beheer, onder Instellingen (alleen voor gespeelde consulten).")


class Inloggen(BaseModel):
    sleutel: str = Field(..., max_length=200)
    code: str = Field("", max_length=10)


@router.post("/api/v1/beheer/inloggen")
async def inloggen(invoer: Inloggen, request: Request):
    _, pogingen = _controleer_poort(request)
    nu = time.time()
    naam = _naam_bij_sleutel(invoer.sleutel)
    geheim = totp_geheimen().get(naam or "")
    if naam is None or (geheim and not totp_klopt(geheim, invoer.code, nu)):
        pogingen.append(nu)
        raise HTTPException(status_code=403, detail="Onjuiste beheersleutel of code.")
    for token in [t for t, (_, tot) in _sessies.items() if tot <= nu]:
        _sessies.pop(token, None)
    token = secrets.token_urlsafe(32)
    tot = nu + _sessie_uren() * 3600
    _sessies[token] = (naam, tot)
    await register.log(naam, "beheer.ingelogd", tweestaps=bool(geheim))
    return {"sessie": token, "naam": naam, "tweestaps": bool(geheim), "geldig_seconden": int(tot - nu)}


@router.post("/api/v1/beheer/uitloggen")
async def uitloggen(sessie: Optional[str] = Header(default=None, alias="X-Beheer-Sessie")):
    if sessie:
        _sessies.pop(sessie.strip(), None)
    return {"ok": True}


CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"


def _pagina(naam: str, csp: str = CSP, referrer: str = "no-referrer") -> FileResponse:
    return FileResponse(STATIC / naam, headers={
        "Cache-Control": "no-store",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": referrer,
        "Content-Security-Policy": csp,
    })


@router.get("/beheer", include_in_schema=False)
async def beheerpagina():
    return _pagina("beheer.html")


@router.get("/beheer/beheer.js", include_in_schema=False)
async def beheerscript():
    return _pagina("beheer.js")


# ── Gegevens ──

PRAKTIJKVELDEN = ("naam", "plaats", "praktijknummers", "agb", "contact_naam", "contact_email", "telefoon",
                  "fte", "werkplekken", "licentietype", "status", "geldig_tot", "serienummer",
                  "eigen_sleutels_verplicht", "brieven_in_eu", "alleen_eu", "notities")


def _json(rij) -> dict:
    uit = {}
    for k, v in dict(rij).items():
        if isinstance(v, date):
            v = v.isoformat()
        elif hasattr(v, "isoformat"):
            v = v.isoformat()
        elif k == "fte" and v is not None:
            v = float(v)
        uit[k] = v
    return uit


class PraktijkInvoer(BaseModel):
    model_config = {"extra": "forbid"}
    naam: Optional[str] = Field(None, max_length=200)
    plaats: Optional[str] = Field(None, max_length=100)
    praktijknummers: Optional[List[str]] = None
    agb: Optional[str] = Field(None, max_length=20)
    contact_naam: Optional[str] = Field(None, max_length=200)
    contact_email: Optional[str] = Field(None, max_length=200)
    telefoon: Optional[str] = Field(None, max_length=40)
    fte: Optional[float] = Field(None, ge=0, le=999)
    werkplekken: Optional[int] = Field(None, ge=0, le=9999)
    licentietype: Optional[str] = None
    status: Optional[str] = None
    geldig_tot: Optional[date] = None
    geldig_tot_leeg: bool = False          # true = onbeperkt (alleen 'intern')
    serienummer: Optional[str] = Field(None, max_length=40)
    eigen_sleutels_verplicht: Optional[bool] = None
    brieven_in_eu: Optional[bool] = None
    alleen_eu: Optional[bool] = None
    notities: Optional[str] = Field(None, max_length=4000)


def _controleer(invoer: PraktijkInvoer) -> dict:
    velden = invoer.model_dump(exclude_unset=True)
    velden.pop("geldig_tot_leeg", None)
    if invoer.geldig_tot_leeg:
        velden["geldig_tot"] = None
    if "licentietype" in velden and velden["licentietype"] not in LICENTIETYPES:
        raise HTTPException(status_code=400, detail="Onbekend licentietype.")
    if "status" in velden and velden["status"] not in STATUSSEN:
        raise HTTPException(status_code=400, detail="Onbekende status.")
    if "praktijknummers" in velden:
        nummers = []
        for n in velden["praktijknummers"] or []:
            n = str(n).strip()
            if not licentie.PRAKTIJKNUMMER.match(n):
                raise HTTPException(status_code=400, detail=f"'{n}' is geen praktijknummer (3 tot 6 cijfers).")
            if n not in nummers:
                nummers.append(n)
        velden["praktijknummers"] = nummers
    if "naam" in velden and not (velden["naam"] or "").strip():
        raise HTTPException(status_code=400, detail="Een praktijk heeft een naam nodig.")
    return velden


async def _praktijk(pid: int) -> dict:
    rij = await register.fetchrow("SELECT * FROM vs_praktijken WHERE id = $1", pid)
    if not rij:
        raise HTTPException(status_code=404, detail="Deze praktijk bestaat niet.")
    return _json(rij)


@router.get("/api/v1/beheer/praktijken")
async def praktijken(_: str = Depends(vereis_beheerder)):
    rijen = await register.fetch(
        """
        SELECT p.*,
               (SELECT count(*) FROM vs_gebruikers g WHERE g.praktijk_id = p.id AND g.actief) AS gebruikers_actief,
               (SELECT count(*) FROM vs_gebruikers g WHERE g.praktijk_id = p.id) AS gebruikers_totaal,
               (SELECT max(laatst_gezien) FROM vs_gebruikers g WHERE g.praktijk_id = p.id) AS laatst_gebruikt,
               COALESCE((SELECT json_agg(json_build_object('dienst', s.dienst, 'aanbieder', s.aanbieder, 'hint', s.hint))
                           FROM vs_praktijk_sleutels s WHERE s.praktijk_id = p.id), '[]'::json) AS eigen_sleutels
          FROM vs_praktijken p
         ORDER BY CASE p.status WHEN 'aangemeld' THEN 0 WHEN 'actief' THEN 1 ELSE 2 END, p.naam
        """
    )
    uit = []
    for r in rijen:
        d = _json(r)
        d["eigen_sleutels"] = json.loads(d["eigen_sleutels"]) if isinstance(d["eigen_sleutels"], str) else d["eigen_sleutels"]
        uit.append(d)
    return {"praktijken": uit, "vandaag": licentie.vandaag().isoformat(), "pilot_maanden": PILOT_MAANDEN}


@router.post("/api/v1/beheer/praktijken")
async def praktijk_maken(invoer: PraktijkInvoer, door: str = Depends(vereis_beheerder)):
    velden = _controleer(invoer)
    if not velden.get("naam"):
        raise HTTPException(status_code=400, detail="Een praktijk heeft een naam nodig.")
    kolommen = [k for k in velden if k in PRAKTIJKVELDEN]
    rij = await register.fetchrow(
        f"INSERT INTO vs_praktijken ({', '.join(kolommen)}) VALUES ({', '.join(f'${i + 1}' for i in range(len(kolommen)))}) RETURNING id",
        *[velden[k] for k in kolommen],
    )
    await register.log(door, "praktijk.gemaakt", rij["id"], naam=velden["naam"])
    return await _praktijk(rij["id"])


@router.patch("/api/v1/beheer/praktijken/{pid}")
async def praktijk_wijzigen(pid: int, invoer: PraktijkInvoer, door: str = Depends(vereis_beheerder)):
    oud = await _praktijk(pid)
    velden = _controleer(invoer)
    # Activeren zonder datum: twaalf maanden vanaf vandaag. Alleen de eigen
    # praktijk (intern) mag onbeperkt; een derde nooit zonder dat je het kiest.
    type_ = velden.get("licentietype", oud["licentietype"])
    if (velden.get("status") == "actief" and "geldig_tot" not in velden and oud["geldig_tot"] is None
            and type_ != "intern"):
        velden["geldig_tot"] = _plus_maanden(licentie.vandaag(), PILOT_MAANDEN)
    kolommen = [k for k in velden if k in PRAKTIJKVELDEN]
    if kolommen:
        zet = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(kolommen))
        await register.execute(f"UPDATE vs_praktijken SET {zet}, bijgewerkt_op = now() WHERE id = $1",
                               pid, *[velden[k] for k in kolommen])
        licentie.wis_cache()
        await register.log(door, "praktijk.gewijzigd", pid,
                           velden={k: (str(velden[k]) if k != "notities" else "…") for k in kolommen})
    return await _praktijk(pid)


@router.post("/api/v1/beheer/praktijken/{pid}/verlengen")
async def praktijk_verlengen(pid: int, door: str = Depends(vereis_beheerder)):
    """Twaalf maanden erbij, vanaf de huidige einddatum of vandaag als die al voorbij is."""
    oud = await _praktijk(pid)
    basis = licentie.vandaag()
    if oud["geldig_tot"]:
        huidig = date.fromisoformat(oud["geldig_tot"])
        basis = max(basis, huidig)
    nieuw = _plus_maanden(basis, PILOT_MAANDEN)
    await register.execute("UPDATE vs_praktijken SET geldig_tot = $2, bijgewerkt_op = now() WHERE id = $1", pid, nieuw)
    licentie.wis_cache()
    await register.log(door, "praktijk.verlengd", pid, tot=nieuw.isoformat())
    return await _praktijk(pid)


@router.delete("/api/v1/beheer/praktijken/{pid}/sleutels/{dienst}")
async def praktijksleutel_verwijderen(pid: int, dienst: str, door: str = Depends(vereis_beheerder)):
    """De beheerder kan een eigen sleutel van een praktijk weghalen, niet lezen."""
    await _praktijk(pid)
    await register.execute("DELETE FROM vs_praktijk_sleutels WHERE praktijk_id = $1 AND dienst = $2", pid, dienst)
    await register.log(door, "praktijk.sleutel_verwijderd", pid, dienst=dienst)
    return await _praktijk(pid)


# ── Gebruikers ──

class GebruikerInvoer(BaseModel):
    model_config = {"extra": "forbid"}
    naam: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    rol: Optional[str] = None
    actief: Optional[bool] = None


GEBRUIKERVELDEN = "id, praktijk_id, naam, email, rol, sleutel_hint, actief, aangemaakt_op, laatst_gezien, laatst_praktijknummer"


@router.get("/api/v1/beheer/praktijken/{pid}/gebruikers")
async def gebruikers(pid: int, _: str = Depends(vereis_beheerder)):
    await _praktijk(pid)
    rijen = await register.fetch(f"SELECT {GEBRUIKERVELDEN} FROM vs_gebruikers WHERE praktijk_id = $1 ORDER BY naam", pid)
    return {"gebruikers": [_json(r) for r in rijen]}


@router.post("/api/v1/beheer/praktijken/{pid}/gebruikers")
async def gebruiker_maken(pid: int, invoer: GebruikerInvoer, door: str = Depends(vereis_beheerder)):
    await _praktijk(pid)
    naam = (invoer.naam or "").strip()
    if not naam:
        raise HTTPException(status_code=400, detail="Een gebruiker heeft een naam nodig.")
    rol = invoer.rol or "gebruiker"
    if rol not in ROLLEN:
        raise HTTPException(status_code=400, detail="Onbekende rol.")
    sleutel = licentie.nieuwe_sleutel()
    rij = await register.fetchrow(
        f"INSERT INTO vs_gebruikers (praktijk_id, naam, email, rol, sleutel_hash, sleutel_hint) "
        f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {GEBRUIKERVELDEN}",
        pid, naam, (invoer.email or "").strip(), rol, licentie.sleutel_hash(sleutel), licentie.hint(sleutel),
    )
    await register.log(door, "gebruiker.gemaakt", pid, gebruiker=rij["id"], rol=rol)
    return {"gebruiker": _json(rij), "sleutel": sleutel}


async def _gebruiker(gid: int) -> dict:
    rij = await register.fetchrow(f"SELECT {GEBRUIKERVELDEN} FROM vs_gebruikers WHERE id = $1", gid)
    if not rij:
        raise HTTPException(status_code=404, detail="Deze gebruiker bestaat niet.")
    return _json(rij)


@router.patch("/api/v1/beheer/gebruikers/{gid}")
async def gebruiker_wijzigen(gid: int, invoer: GebruikerInvoer, door: str = Depends(vereis_beheerder)):
    oud = await _gebruiker(gid)
    velden = invoer.model_dump(exclude_unset=True)
    if "rol" in velden and velden["rol"] not in ROLLEN:
        raise HTTPException(status_code=400, detail="Onbekende rol.")
    if "naam" in velden and not (velden["naam"] or "").strip():
        raise HTTPException(status_code=400, detail="Een gebruiker heeft een naam nodig.")
    if velden:
        kolommen = list(velden)
        zet = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(kolommen))
        await register.execute(f"UPDATE vs_gebruikers SET {zet} WHERE id = $1", gid, *[velden[k] for k in kolommen])
        licentie.wis_cache()
        await register.log(door, "gebruiker.gewijzigd", oud["praktijk_id"], gebruiker=gid,
                           velden={k: str(v) for k, v in velden.items() if k != "email"})
    return await _gebruiker(gid)


@router.post("/api/v1/beheer/gebruikers/{gid}/nieuwe-sleutel")
async def gebruiker_nieuwe_sleutel(gid: int, door: str = Depends(vereis_beheerder)):
    """Een nieuwe sleutel; de oude werkt direct niet meer."""
    oud = await _gebruiker(gid)
    sleutel = licentie.nieuwe_sleutel()
    await register.execute("UPDATE vs_gebruikers SET sleutel_hash = $2, sleutel_hint = $3 WHERE id = $1",
                           gid, licentie.sleutel_hash(sleutel), licentie.hint(sleutel))
    licentie.wis_cache()
    await register.log(door, "gebruiker.nieuwe_sleutel", oud["praktijk_id"], gebruiker=gid)
    return {"gebruiker": await _gebruiker(gid), "sleutel": sleutel}


# ── Instellingen, log en export ──

class Instellingen(BaseModel):
    model_config = {"extra": "forbid"}
    tarief_per_fte: Optional[float] = Field(None, ge=0, le=1_000_000)
    serveradres: Optional[str] = Field(None, max_length=200)
    winkellink: Optional[str] = Field(None, max_length=500)
    testgereedschap: Optional[bool] = None
    stilte_inkorten: Optional[bool] = None


# Switches stored as "aan"/"uit"; who flipped them, and when, stays in the admin log.
SCHAKELAARS = (TESTGEREEDSCHAP, "stilte_inkorten")


@router.get("/api/v1/beheer/instellingen")
async def instellingen_lezen(_: str = Depends(vereis_beheerder)):
    rijen = await register.fetch("SELECT sleutel, waarde FROM vs_instellingen")
    uit = {r["sleutel"]: r["waarde"] for r in rijen}
    return {
        "tarief_per_fte": float(uit["tarief_per_fte"]) if uit.get("tarief_per_fte") else None,
        "serveradres": uit.get("serveradres", ""),
        "winkellink": uit.get("winkellink", ""),
        "testgereedschap": uit.get(TESTGEREEDSCHAP) == "aan",
        "stilte_inkorten": uit.get("stilte_inkorten") == "aan",
    }


@router.put("/api/v1/beheer/instellingen")
async def instellingen_opslaan(invoer: Instellingen, door: str = Depends(vereis_beheerder)):
    for k, v in invoer.model_dump(exclude_unset=True).items():
        if k in SCHAKELAARS:
            if v is None:
                continue
            await register.execute(
                "INSERT INTO vs_instellingen (sleutel, waarde) VALUES ($1, $2) "
                "ON CONFLICT (sleutel) DO UPDATE SET waarde = EXCLUDED.waarde", k, "aan" if v else "uit")
            await register.log(door, f"{k}.aan" if v else f"{k}.uit")
            continue
        await register.execute(
            "INSERT INTO vs_instellingen (sleutel, waarde) VALUES ($1, $2) "
            "ON CONFLICT (sleutel) DO UPDATE SET waarde = EXCLUDED.waarde", k, "" if v is None else str(v))
    await register.log(door, "instellingen.gewijzigd")
    return await instellingen_lezen(door)


@router.get("/api/v1/beheer/log")
async def beheerlog(_: str = Depends(vereis_beheerder)):
    rijen = await register.fetch(
        "SELECT l.op, l.door, l.handeling, l.praktijk_id, p.naam AS praktijk, l.details "
        "FROM vs_beheerlog l LEFT JOIN vs_praktijken p ON p.id = l.praktijk_id ORDER BY l.op DESC LIMIT 200")
    uit = []
    for r in rijen:
        d = _json(r)
        d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
        uit.append(d)
    return {"log": uit}


@router.get("/api/v1/beheer/auditlog")
async def auditlog(gebruiker: str = "", dagen: int = 30, _: str = Depends(vereis_beheerder)):
    """Het gebruikslog (NEN 7513) om na te lopen: de laatste dagen, eventueel van
    één gebruiker. Hoogstens duizend regels per keer."""
    dagen = min(max(dagen, 1), 3660)
    rijen = await register.fetch(
        "SELECT op, gebruiker, handeling, details FROM vs_auditlog "
        "WHERE op >= now() - make_interval(days => $1) AND ($2 = '' OR gebruiker = $2) "
        "ORDER BY op DESC LIMIT 1000", dagen, gebruiker.strip())
    uit = []
    for r in rijen:
        d = _json(r)
        d["details"] = json.loads(d["details"]) if isinstance(d["details"], str) else d["details"]
        uit.append(d)
    return {"log": uit, "bewaardagen": audit.retention_days()}


# ── AI-gebruik en geschatte kosten (kosten.py) ──

_PRIJSVELDEN = ("in", "uit", "cache_w", "cache_w1h", "cache_r", "minuut", "tekens")


@router.get("/api/v1/beheer/kosten")
async def kostenoverzicht(dagen: int = 30, _: str = Depends(vereis_beheerder)):
    """Wat VitaScribe aan AI afnam, per dienst en model, met een schatting in geld."""
    from . import kosten
    return await kosten.overzicht(min(max(dagen, 1), 400))


class Prijzen(BaseModel):
    prijzen: Dict[str, Optional[Dict[str, object]]] = Field(default_factory=dict)


@router.put("/api/v1/beheer/kosten/prijzen")
async def prijzen_opslaan(invoer: Prijzen, door: str = Depends(vereis_beheerder)):
    """Eigen prijzen (uit de facturen), per prijsregel. null haalt een eigen prijs weg."""
    from . import kosten
    schoon: Dict[str, Optional[dict]] = {}
    for sleutel, waarden in invoer.prijzen.items():
        sleutel = str(sleutel).strip()[:80]
        if not sleutel:
            continue
        if waarden is None:
            schoon[sleutel] = None
            continue
        regel: dict = {}
        for veld in _PRIJSVELDEN:
            w = waarden.get(veld)
            if w in (None, ""):
                continue
            try:
                getal = float(str(w).replace(",", "."))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Prijs voor {sleutel} ({veld}) is geen getal.")
            if getal < 0 or getal > 1000:
                raise HTTPException(status_code=400, detail=f"Prijs voor {sleutel} ({veld}) is niet aannemelijk.")
            regel[veld] = getal
        valuta = str(waarden.get("valuta") or "USD").upper()
        if valuta not in ("USD", "EUR"):
            raise HTTPException(status_code=400, detail="Valuta is USD of EUR.")
        regel["valuta"] = valuta
        schoon[sleutel] = regel
    huidig = dict(await kosten.eigen_prijzen())
    for k, v in schoon.items():
        if v is None:
            huidig.pop(k, None)
        else:
            huidig[k] = v
    await kosten.zet_eigen_prijzen(huidig)
    await register.log(door, "kosten.prijzen", sleutels=sorted(schoon))
    return {"prijzen": kosten.prijzen(huidig)}


@router.get("/api/v1/beheer/export")
async def export(_: str = Depends(vereis_beheerder)):
    """Het register als JSON, om naast de database te bewaren. Zonder sleutels
    van gebruikers (die bestaan nergens) en zonder de versleutelde sleutels van
    praktijken (alleen welke dienst en aanbieder)."""
    praktijk_rijen = await register.fetch("SELECT * FROM vs_praktijken ORDER BY id")
    gebruiker_rijen = await register.fetch(f"SELECT {GEBRUIKERVELDEN} FROM vs_gebruikers ORDER BY id")
    sleutel_rijen = await register.fetch("SELECT praktijk_id, dienst, aanbieder, hint, ingesteld_op FROM vs_praktijk_sleutels")
    inhoud = {
        "gemaakt_op": licentie.vandaag().isoformat(),
        "praktijken": [_json(r) for r in praktijk_rijen],
        "gebruikers": [_json(r) for r in gebruiker_rijen],
        "eigen_sleutels": [_json(r) for r in sleutel_rijen],
    }
    return JSONResponse(inhoud, headers={
        "Content-Disposition": f'attachment; filename="vitascribe-register-{inhoud["gemaakt_op"]}.json"',
        "Cache-Control": "no-store",
    })
