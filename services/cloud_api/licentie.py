"""
VitaScribe Cloud API - Wie is dit, en mag deze praktijk VitaScribe gebruiken?

Elke aanroep draagt een sleutel (X-API-Key). Die hoort bij één van drie bronnen:

  omgeving   API_USERS / API_KEYS, zoals voorheen. Blijft werken, zodat de eigen
             praktijk en bestaande werkplekken niet stilvallen als het register
             aangaat.
  register   een gebruiker in vs_gebruikers, bij een praktijk met een licentie.
  dev        geen sleutels in de omgeving én geen register: alles mag. Staat
             het register aan, dan bestaat deze modus niet meer.

Voor een registersleutel gelden dezelfde regels als bij Bricks Companion, maar
nu op de server, zodat uitzetten direct werkt:

- de gebruiker staat aan, de praktijk heeft status 'actief', en de licentie is
  niet verlopen;
- praktijkbinding: de extensie stuurt de nummers mee die zij in de Bricks-URL
  ziet (X-Bricks-Praktijk). Noemt de licentie praktijknummers en hoort het
  dossier herkenbaar bij een ándere praktijk, dan weigert de server. Ziet de
  extensie geen nummer, dan gaat het door: een huisarts mag nooit midden in het
  spreekuur worden geblokkeerd omdat Tetra de URL-opbouw wijzigt.

Sleutels staan als sha256 in de database. Het zijn willekeurige tekenreeksen van
256 bits, dus een trage wachtwoordhash voegt niets toe.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import structlog

from . import register

logger = structlog.get_logger()

AMSTERDAM = ZoneInfo("Europe/Amsterdam")
PRAKTIJKNUMMER = re.compile(r"^\d{3,6}$")
CACHE_SECONDEN = 30          # na uitzetten werkt een sleutel hooguit zo lang door
NOODCACHE_SECONDEN = 3600    # database even weg: een sleutel die zo kort geleden goed was, blijft werken
GEZIEN_INTERVAL = 300        # laatst_gezien hooguit eens per vijf minuten bijwerken


class LicentieFout(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class Identiteit:
    label: str                       # zoals het in het gebruikslog komt
    bron: str                        # 'omgeving' | 'register' | 'dev'
    gebruiker_id: Optional[int] = None
    gebruiker_naam: str = ""
    rol: str = "gebruiker"
    praktijk_id: Optional[int] = None
    praktijk_naam: str = ""
    licentietype: str = ""
    geldig_tot: Optional[date] = None
    praktijknummers: List[str] = field(default_factory=list)
    eigen_sleutels_verplicht: bool = False
    brieven_in_eu: bool = False

    @property
    def is_praktijkbeheerder(self) -> bool:
        return self.bron == "register" and self.rol == "praktijkbeheerder"


# ── Sleutels ──

def nieuwe_sleutel() -> str:
    return "vs_" + secrets.token_urlsafe(32)


def sleutel_hash(sleutel: str) -> str:
    return hashlib.sha256(sleutel.encode("utf-8")).hexdigest()


def hint(sleutel: str) -> str:
    """De laatste vier tekens, om een sleutel te herkennen zonder hem te tonen."""
    return sleutel[-4:] if len(sleutel) >= 8 else "····"


# ── Praktijknummers ──

def praktijknummers_uit_kop(waarde: Optional[str]) -> List[str]:
    """X-Bricks-Praktijk: kommagescheiden nummers. Alles wat er niet als een
    praktijknummer uitziet, valt weg; hooguit vier."""
    if not waarde:
        return []
    uit: List[str] = []
    for deel in str(waarde).split(","):
        deel = deel.strip()
        if PRAKTIJKNUMMER.match(deel) and deel not in uit:
            uit.append(deel)
    return uit[:4]


def binding_fout(toegestaan: List[str], gevonden: List[str]) -> Optional[str]:
    """Een melding als het dossier bij een andere praktijk hoort, anders None."""
    lijst = [p for p in (toegestaan or []) if p]
    if not lijst or not gevonden:
        return None
    if any(n in lijst for n in gevonden):
        return None
    return (f"Deze licentie geldt voor praktijknummer {', '.join(lijst)}; "
            f"dit Bricks-dossier hoort bij praktijk {gevonden[0]}.")


def vandaag() -> date:
    return datetime.now(AMSTERDAM).date()


# ── Opzoeken ──

_cache: Dict[str, Tuple[float, Optional[dict]]] = {}
_gezien: Dict[int, float] = {}


def wis_cache() -> None:
    """Na elke wijziging in het beheer, zodat die meteen geldt."""
    _cache.clear()


async def _zoek(h: str) -> Optional[dict]:
    nu = time.monotonic()
    raak = _cache.get(h)
    if raak and nu - raak[0] < CACHE_SECONDEN:
        return raak[1]
    try:
        rij = await _haal(h)
    except Exception as exc:
        # Een huisarts mag niet stilvallen omdat de database even weg is: een
        # sleutel die kort geleden nog klopte, blijft zolang werken.
        logger.error("licentie.database_onbereikbaar", error=str(exc))
        if raak and raak[1] is not None and nu - raak[0] < NOODCACHE_SECONDEN:
            return raak[1]
        raise LicentieFout(503, "De licentiecontrole is even niet bereikbaar. Probeer het over een minuut opnieuw.")
    waarde = dict(rij) if rij else None
    _cache[h] = (nu, waarde)
    return waarde


async def _haal(h: str):
    return await register.fetchrow(
        """
        SELECT g.id AS gebruiker_id, g.naam AS gebruiker_naam, g.rol, g.actief AS gebruiker_actief,
               p.id AS praktijk_id, p.naam AS praktijk_naam, p.status, p.licentietype, p.geldig_tot,
               p.praktijknummers, p.eigen_sleutels_verplicht, p.brieven_in_eu
          FROM vs_gebruikers g JOIN vs_praktijken p ON p.id = g.praktijk_id
         WHERE g.sleutel_hash = $1
        """,
        h,
    )


async def _markeer_gezien(gebruiker_id: int, nummer: Optional[str]) -> None:
    nu = time.monotonic()
    # Niet vergelijken met 0: de monotone klok telt vanaf het opstarten van de
    # machine, en in een net gestarte container is die nog geen vijf minuten.
    vorige = _gezien.get(gebruiker_id)
    if vorige is not None and nu - vorige < GEZIEN_INTERVAL:
        return
    _gezien[gebruiker_id] = nu
    try:
        await register.execute(
            "UPDATE vs_gebruikers SET laatst_gezien = now(), "
            "laatst_praktijknummer = COALESCE($2, laatst_praktijknummer) WHERE id = $1",
            gebruiker_id, nummer,
        )
    except Exception as exc:
        logger.error("licentie.gezien_mislukt", error=str(exc))


def _omgevingstabel() -> Dict[str, str]:
    from .auth import _key_table  # één plek voor het lezen van API_USERS/API_KEYS
    return _key_table()


async def identificeer(sleutel: Optional[str], praktijk_kop: Optional[str] = None) -> Identiteit:
    """De identiteit bij een sleutel, of LicentieFout met een melding voor de arts."""
    tabel = _omgevingstabel()
    if not tabel and not register.actief():
        from .auth import open_mode
        if open_mode():
            return Identiteit(label="dev", bron="dev")
        raise LicentieFout(503, "De server heeft geen sleutels en geen register. "
                                "Neem contact op met de beheerder van VitaScribe.")
    if not sleutel:
        raise LicentieFout(401, "API sleutel ontbreekt.")

    for key, naam in tabel.items():
        if hmac.compare_digest(key, sleutel):
            return Identiteit(label=naam, bron="omgeving", gebruiker_naam=naam)

    if not register.actief():
        raise LicentieFout(403, "Ongeldige API sleutel.")

    rij = await _zoek(sleutel_hash(sleutel))
    if rij is None:
        raise LicentieFout(403, "Ongeldige API sleutel.")
    if not rij["gebruiker_actief"]:
        raise LicentieFout(403, "Deze sleutel is uitgezet. Vraag de beheerder van VitaScribe om een nieuwe.")
    naam = rij["praktijk_naam"]
    if rij["status"] != "actief":
        raise LicentieFout(403, f"De licentie van {naam} is niet actief. Neem contact op met de beheerder van VitaScribe.")
    tot = rij["geldig_tot"]
    if tot is not None and tot < vandaag():
        raise LicentieFout(403, f"De licentie van {naam} is verlopen op {tot.strftime('%d-%m-%Y')}. "
                                "Neem contact op voor verlenging.")

    gevonden = praktijknummers_uit_kop(praktijk_kop)
    fout = binding_fout(list(rij["praktijknummers"] or []), gevonden)
    if fout:
        raise LicentieFout(403, fout)

    await _markeer_gezien(rij["gebruiker_id"], gevonden[0] if gevonden else None)
    return Identiteit(
        label=f"{rij['gebruiker_naam']} ({naam})",
        bron="register",
        gebruiker_id=rij["gebruiker_id"],
        gebruiker_naam=rij["gebruiker_naam"],
        rol=rij["rol"],
        praktijk_id=rij["praktijk_id"],
        praktijk_naam=naam,
        licentietype=rij["licentietype"],
        geldig_tot=tot,
        praktijknummers=list(rij["praktijknummers"] or []),
        eigen_sleutels_verplicht=bool(rij["eigen_sleutels_verplicht"]),
        brieven_in_eu=bool(rij["brieven_in_eu"]),
    )
