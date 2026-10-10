"""
VitaScribe Cloud API - AI-gebruik en geschatte kosten

Wat VitaScribe zelf bij de AI-diensten afneemt, geteld op de plek waar het
gebeurt: tokens per taalmodel, seconden spraak, tekens voorlezen. Nooit
inhoud. Twee toepassingen:

  1. Het overzicht in Beheer (/api/v1/beheer/kosten): per dag, per dienst en
     model, met een schatting in geld. Opgeslagen in vs_ai_gebruik (register);
     zonder register alleen in het geheugen, tot de server herstart.
  2. Per consult: terwijl de server één consult verwerkt (meten()), telt hij
     wat bij dat consult hoort en geeft het totaal mee in het verslag
     ("kosten"), zodat de arts onderaan ziet wat het consult aan AI kostte.

Het blijft een schatting. De factuur van de aanbieder is leidend: daar staan
ook kortingen, minimumbedragen, btw en de wisselkoers in. Standaard rekent het
met de openbare lijstprijzen (STANDAARD_PRIJZEN, met bron en datum), zodat het
vooraf kan schatten; de beheerder kan elke prijs vervangen door die op de
factuur (vs_instellingen 'kosten_prijzen'). Een dienst zonder bekende prijs
toont de hoeveelheid en "prijs onbekend", zonder gok.

Gebruik buiten VitaScribe (Claude.ai, andere apps op dezelfde sleutel) komt
hier niet in: dat ziet alleen de aanbieder.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

PRIJZEN_PER = "2026-10-10"

# Prices per unit. Tokens: per million (in, uit, cache_w, cache_w1h, cache_r). Speech:
# per minute. Voices: per million characters. Public list prices, looked up on
# PRIJZEN_PER, so the overview can estimate in advance; where sources
# disagreed, the higher price (an estimate should not turn out too low). Cache
# writes at 1.25x the input price for the 5-minute cache (cache_w) and 2x for
# the 1-hour cache (cache_w1h, added 2026-10-10); reads at 0.1x for both.
# The administrator can override any of them with the price on the invoice.
STANDAARD_PRIJZEN: Dict[str, dict] = {
    # Anthropic, list prices.
    "anthropic:claude-sonnet-5": {"in": 2.00, "uit": 10.00, "cache_w": 2.50, "cache_w1h": 4.00, "cache_r": 0.20, "valuta": "USD",
                                  "bron": "lijstprijs Anthropic; 1-uurscache 2x invoer, per 2026-10-10"},
    "anthropic:claude-sonnet-5-5": {"in": 2.00, "uit": 10.00, "cache_w": 2.50, "cache_w1h": 4.00, "cache_r": 0.20, "valuta": "USD",
                                    "bron": "lijstprijs Anthropic; 1-uurscache 2x invoer, per 2026-10-10"},
    "anthropic:claude-haiku-5-5": {"in": 0.10, "uit": 0.50, "cache_w": 0.125, "cache_w1h": 0.20, "cache_r": 0.01, "valuta": "USD",
                                   "bron": "lijstprijs Anthropic (tot 100K tokens per vraag); 1-uurscache 2x invoer, per 2026-10-10"},
    "anthropic:claude-haiku-4-5": {"in": 1.00, "uit": 5.00, "cache_w": 1.25, "cache_w1h": 2.00, "cache_r": 0.10, "valuta": "USD",
                                   "bron": "lijstprijs Anthropic; 1-uurscache 2x invoer, per 2026-10-10"},
    # Mistral (EU), list prices on mistral.ai/pricing (Large 3, Small 4).
    "mistral:mistral-large-latest": {"in": 0.50, "uit": 1.50, "valuta": "USD", "bron": "lijstprijs Mistral (Large)"},
    "mistral:mistral-small-latest": {"in": 0.15, "uit": 0.60, "valuta": "USD", "bron": "lijstprijs Mistral (Small)"},
    # Speech recognition, per minute.
    "deepgram": {"minuut": 0.0043, "valuta": "USD", "bron": "lijstprijs Deepgram Nova-3, achteraf"},
    "deepgram_live": {"minuut": 0.0077, "valuta": "USD", "bron": "lijstprijs Deepgram Nova-3, live (zonder actiekorting)"},
    "voxtral": {"minuut": 0.003, "valuta": "USD", "bron": "lijstprijs Mistral Voxtral"},
    "gladia": {"minuut": 0.0102, "valuta": "USD", "bron": "lijstprijs Gladia, pay-as-you-go ($0,61 per uur)"},
    "speechmatics": {"minuut": 0.0125, "valuta": "USD",
                     "bron": "Speechmatics Enhanced, achteraf ($0,40–1,04 per uur in bronnen; hier $0,75)"},
    # Reading aloud, per million characters.
    "azure_tts": {"tekens": 16.0, "valuta": "USD", "bron": "lijstprijs Azure neurale stem"},
    "mistral_tts": {"tekens": 16.0, "valuta": "USD", "bron": "lijstprijs Mistral Voxtral TTS"},
}

# Which price row a usage row belongs to.
def prijssleutel(dienst: str, model: str) -> str:
    model = (model or "").lower()
    if dienst == "anthropic":
        for basis in ("claude-sonnet-5-5", "claude-sonnet-5", "claude-haiku-5-5", "claude-haiku-4-5", "claude-opus-5-5"):
            if model.startswith(basis):
                return f"anthropic:{basis}"
        return f"anthropic:{model}"
    if dienst in ("mistral", "bedrock"):
        return f"{dienst}:{model}"
    if dienst in ("azure_tts", "mistral_tts"):
        return dienst
    return dienst   # speech services: one price per minute


# ── Counting ──

@dataclass
class Regel:
    aanroepen: int = 0
    in_tokens: int = 0
    uit_tokens: int = 0
    cache_w: int = 0      # 5-minute cache writes (and every write before 2026-10-10)
    cache_w1h: int = 0    # 1-hour cache writes, priced at 2x input
    cache_r: int = 0
    seconden: float = 0.0
    tekens: int = 0

    def tel(self, ander: "Regel") -> None:
        self.aanroepen += ander.aanroepen
        self.in_tokens += ander.in_tokens
        self.uit_tokens += ander.uit_tokens
        self.cache_w += ander.cache_w
        self.cache_w1h += ander.cache_w1h
        self.cache_r += ander.cache_r
        self.seconden += ander.seconden
        self.tekens += ander.tekens


@dataclass
class Teller:
    """What one consult used: (dienst, model, soort) -> Regel."""
    regels: Dict[Tuple[str, str, str], Regel] = field(default_factory=dict)

    def voeg_toe(self, sleutel: Tuple[str, str, str], regel: Regel) -> None:
        self.regels.setdefault(sleutel, Regel()).tel(regel)


_teller: contextvars.ContextVar[Optional[Teller]] = contextvars.ContextVar("vs_kosten_teller", default=None)

# ── Which part of VitaScribe used it: for the breakdown (speech, thinking along, report, ...) ──

SPRAAKDIENSTEN = {"deepgram", "deepgram_live", "voxtral", "gladia", "speechmatics", "groq", "openai"}

# The request decides the part (main.py sets it per request); within one request
# a function can name its own part (als / onderdeel), e.g. nazorg within a consult.
_onderdeel: contextvars.ContextVar[str] = contextvars.ContextVar("vs_onderdeel", default="")

ONDERDEEL_PER_PAD = [
    ("/api/v1/consult/", "verslaglegging"), ("/api/v1/dictation/", "dicteren"), ("/api/v1/tolk/", "tolk"),
    ("/api/v1/telefoon/", "tolk"), ("/api/v1/visite/", "visite"), ("/api/v1/dossier/", "dossiervraag"),
    ("/api/v1/letters", "brieven"), ("/api/v1/post", "post en uitslagen"), ("/api/v1/econsult", "e-consult"),
    ("/api/v1/soep", "meedenken"), ("/api/v1/patient", "patiëntinformatie"), ("/api/v1/leren", "leren"),
    ("/api/v1/beheer/", "testen"),
]


def onderdeel_voor_pad(pad: str) -> str:
    for begin, naam in ONDERDEEL_PER_PAD:
        if (pad or "").startswith(begin):
            return naam
    return "overig"


def onderdeel_van(dienst: str) -> str:
    """Speech and voices by their service; everything else by the part that called it."""
    if dienst in SPRAAKDIENSTEN:
        return "spraakherkenning"
    if dienst.endswith("_tts"):
        return "voorlezen"
    return _onderdeel.get() or "overig"


class als:
    """with kosten.als("nazorg en afspraken"): calls inside count for that part."""

    def __init__(self, naam: str) -> None:
        self.naam = naam

    def __enter__(self) -> None:
        self._token = _onderdeel.set(self.naam)

    def __exit__(self, *exc) -> None:
        _onderdeel.reset(self._token)


def onderdeel(naam: str):
    """Decorator for an async function whose AI calls belong to one part."""
    import functools

    def wrap(fn):
        @functools.wraps(fn)
        async def binnen(*args, **kwargs):
            with als(naam):
                return await fn(*args, **kwargs)
        return binnen
    return wrap

# Without a register: today's and earlier days' totals in memory, until a restart.
_geheugen: Dict[Tuple[str, str, str, str], Regel] = {}
_taken: set = set()


def _int(x) -> int:
    try:
        return int(x or 0)
    except (TypeError, ValueError):
        return 0


def tel(dienst: str, model: str = "", soort: str = "", *, in_tokens=0, uit_tokens=0, cache_w=0, cache_r=0,
        seconden=0.0, tekens=0, cache_w1h=0) -> None:
    """Count one use. Never raises: counting must not break the work itself."""
    try:
        regel = Regel(aanroepen=1, in_tokens=_int(in_tokens), uit_tokens=_int(uit_tokens), cache_w=_int(cache_w),
                      cache_w1h=_int(cache_w1h), cache_r=_int(cache_r), seconden=float(seconden or 0), tekens=_int(tekens))
        # The stored "soort" is the part of VitaScribe (spraakherkenning, verslaglegging, meedenken, ...).
        sleutel = (dienst, model or "", onderdeel_van(dienst))
        t = _teller.get()
        if t is not None:
            t.voeg_toe(sleutel, regel)
        dag = datetime.now(timezone.utc).date().isoformat()
        _geheugen.setdefault((dag,) + sleutel, Regel()).tel(regel)
        from . import register
        if register.actief():
            try:
                taak = asyncio.get_running_loop().create_task(_bewaar(dag, sleutel, regel))
                _taken.add(taak)
                taak.add_done_callback(_taken.discard)
            except RuntimeError:
                pass   # no event loop (a test or a script): memory only
    except Exception as exc:
        logger.warning("kosten.tel_fout", error=type(exc).__name__)


async def _bewaar(dag: str, sleutel: Tuple[str, str, str], r: Regel) -> None:
    from . import register
    try:
        await register.execute(
            "INSERT INTO vs_ai_gebruik (dag, dienst, model, soort, aanroepen, in_tokens, uit_tokens, cache_w, cache_r, "
            "seconden, tekens, cache_w1h) VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) "
            "ON CONFLICT (dag, dienst, model, soort) DO UPDATE SET "
            "aanroepen = vs_ai_gebruik.aanroepen + EXCLUDED.aanroepen, "
            "in_tokens = vs_ai_gebruik.in_tokens + EXCLUDED.in_tokens, "
            "uit_tokens = vs_ai_gebruik.uit_tokens + EXCLUDED.uit_tokens, "
            "cache_w = vs_ai_gebruik.cache_w + EXCLUDED.cache_w, cache_r = vs_ai_gebruik.cache_r + EXCLUDED.cache_r, "
            "cache_w1h = vs_ai_gebruik.cache_w1h + EXCLUDED.cache_w1h, "
            "seconden = vs_ai_gebruik.seconden + EXCLUDED.seconden, tekens = vs_ai_gebruik.tekens + EXCLUDED.tekens",
            date.fromisoformat(dag), *sleutel, r.aanroepen, r.in_tokens, r.uit_tokens, r.cache_w, r.cache_r,
            r.seconden, r.tekens, r.cache_w1h)
    except Exception as exc:
        logger.warning("kosten.bewaar_fout", error=type(exc).__name__)


def huidige() -> Optional[Teller]:
    """The teller of the consult being processed now, if any."""
    return _teller.get()


class meten:
    """with kosten.meten() as teller: everything counted inside (also in tasks
    started inside) goes into this consult's teller as well."""

    def __enter__(self) -> Teller:
        self.teller = Teller()
        self._token = _teller.set(self.teller)
        return self.teller

    def __exit__(self, *exc) -> None:
        _teller.reset(self._token)


# ── Prices and amounts ──

def prijzen(eigen: Optional[dict] = None) -> Dict[str, dict]:
    """Standard prices, overridden or added to by the administrator's."""
    uit = {k: dict(v) for k, v in STANDAARD_PRIJZEN.items()}
    for k, v in (eigen or {}).items():
        if v is None:
            uit.pop(k, None)
        elif isinstance(v, dict):
            uit[k] = {**{"bron": "ingevuld in Beheer"}, **v}
    return uit


def bedrag(dienst: str, model: str, r: Regel, tabel: Dict[str, dict]) -> Optional[Tuple[float, str]]:
    """(amount, currency), or None when no price is known."""
    p = tabel.get(prijssleutel(dienst, model))
    if not p:
        return None
    som = 0.0
    bekend = False
    for veld, aantal, deler in (("in", r.in_tokens, 1e6), ("uit", r.uit_tokens, 1e6), ("cache_w", r.cache_w, 1e6),
                                ("cache_w1h", r.cache_w1h, 1e6), ("cache_r", r.cache_r, 1e6), ("minuut", r.seconden, 60.0), ("tekens", r.tekens, 1e6)):
        if aantal and p.get(veld) is not None:
            som += float(p[veld]) * aantal / deler
            bekend = True
        elif aantal and p.get(veld) is None and veld not in ("cache_w", "cache_w1h", "cache_r"):
            return None   # a quantity without a price: no guess
    return (som, str(p.get("valuta") or "USD")) if bekend or not any(
        (r.in_tokens, r.uit_tokens, r.seconden, r.tekens)) else None


def samenvatting(teller: Teller, tabel: Optional[Dict[str, dict]] = None) -> dict:
    """For the report: total per currency and what had no price."""
    tabel = tabel if tabel is not None else prijzen(_eigen_cache)
    totaal: Dict[str, float] = {}
    per_onderdeel: Dict[str, Dict[str, float]] = {}
    onbekend: List[str] = []
    for (dienst, model, deel), r in teller.regels.items():
        b = bedrag(dienst, model, r, tabel)
        if b is None:
            naam = f"{dienst} {model}".strip()
            if naam not in onbekend:
                onbekend.append(naam)
            continue
        totaal[b[1]] = totaal.get(b[1], 0.0) + b[0]
        per_onderdeel.setdefault(deel or "overig", {})
        per_onderdeel[deel or "overig"][b[1]] = per_onderdeel[deel or "overig"].get(b[1], 0.0) + b[0]
    return {"totaal": {k: round(v, 4) for k, v in totaal.items()}, "onbekend": onbekend,
            "per_onderdeel": {d: {k: round(v, 4) for k, v in w.items()} for d, w in
                              sorted(per_onderdeel.items(), key=lambda x: -sum(x[1].values()))},
            "aanroepen": sum(r.aanroepen for r in teller.regels.values()), "prijzen_per": PRIJZEN_PER}


# The administrator's prices, read from the register now and then (the report needs them without waiting).
_eigen_cache: dict = {}
_eigen_tijd = 0.0


async def eigen_prijzen() -> dict:
    global _eigen_cache, _eigen_tijd
    from . import register
    if not register.actief():
        return _eigen_cache
    if time.time() - _eigen_tijd < 300:
        return _eigen_cache
    try:
        rij = await register.fetchrow("SELECT waarde FROM vs_instellingen WHERE sleutel = 'kosten_prijzen'")
        _eigen_cache = json.loads(rij["waarde"]) if rij else {}
    except Exception as exc:
        logger.warning("kosten.prijzen_fout", error=type(exc).__name__)
    _eigen_tijd = time.time()
    return _eigen_cache


async def zet_eigen_prijzen(nieuw: dict) -> dict:
    global _eigen_cache, _eigen_tijd
    from . import register
    _eigen_cache = nieuw
    _eigen_tijd = time.time()
    if register.actief():
        await register.execute(
            "INSERT INTO vs_instellingen (sleutel, waarde) VALUES ('kosten_prijzen', $1) "
            "ON CONFLICT (sleutel) DO UPDATE SET waarde = EXCLUDED.waarde", json.dumps(nieuw))
    return nieuw


async def gebruik(dagen: int) -> List[dict]:
    """Usage rows of the last days: [{dag, dienst, model, soort, ...}]."""
    from . import register
    vanaf = (datetime.now(timezone.utc).date() - timedelta(days=dagen - 1))
    if register.actief():
        rijen = await register.fetch(
            "SELECT dag, dienst, model, soort, aanroepen, in_tokens, uit_tokens, cache_w, cache_r, seconden, tekens, "
            "cache_w1h "
            "FROM vs_ai_gebruik WHERE dag >= $1 ORDER BY dag", vanaf)
        return [{**dict(r), "dag": r["dag"].isoformat()} for r in rijen]
    uit = []
    for (dag, dienst, model, soort), r in sorted(_geheugen.items()):
        if dag >= vanaf.isoformat():
            uit.append({"dag": dag, "dienst": dienst, "model": model, "soort": soort, "aanroepen": r.aanroepen,
                        "in_tokens": r.in_tokens, "uit_tokens": r.uit_tokens, "cache_w": r.cache_w,
                        "cache_w1h": r.cache_w1h, "cache_r": r.cache_r, "seconden": r.seconden, "tekens": r.tekens})
    return uit


async def overzicht(dagen: int) -> dict:
    """For Beheer: per service and model, per day, totals and an estimate per month."""
    from . import register
    tabel = prijzen(await eigen_prijzen())
    rijen = await gebruik(dagen)
    per_model: Dict[Tuple[str, str], Regel] = {}
    per_dag: Dict[str, Dict[str, float]] = {}
    per_deel: Dict[str, Dict[str, float]] = {}
    aanroepen_deel: Dict[str, int] = {}
    onbekend = set()
    for rij in rijen:
        r = Regel(**{k: rij[k] for k in ("aanroepen", "in_tokens", "uit_tokens", "cache_w", "cache_r", "seconden",
                                         "tekens")}, cache_w1h=rij.get("cache_w1h") or 0)
        per_model.setdefault((rij["dienst"], rij["model"]), Regel()).tel(r)
        b = bedrag(rij["dienst"], rij["model"], r, tabel)
        dag = per_dag.setdefault(rij["dag"], {})
        deel = rij.get("soort") or "overig"
        aanroepen_deel[deel] = aanroepen_deel.get(deel, 0) + r.aanroepen
        if b is None:
            onbekend.add(f"{rij['dienst']} {rij['model']}".strip())
        else:
            dag[b[1]] = dag.get(b[1], 0.0) + b[0]
            per_deel.setdefault(deel, {})
            per_deel[deel][b[1]] = per_deel[deel].get(b[1], 0.0) + b[0]
    regels = []
    totaal: Dict[str, float] = {}
    for (dienst, model), r in sorted(per_model.items()):
        b = bedrag(dienst, model, r, tabel)
        if b:
            totaal[b[1]] = totaal.get(b[1], 0.0) + b[0]
        regels.append({"dienst": dienst, "model": model, "sleutel": prijssleutel(dienst, model),
                       "aanroepen": r.aanroepen, "in_tokens": r.in_tokens, "uit_tokens": r.uit_tokens,
                       "cache_w": r.cache_w, "cache_w1h": r.cache_w1h, "cache_r": r.cache_r, "minuten": round(r.seconden / 60, 1),
                       "tekens": r.tekens, "kosten": round(b[0], 4) if b else None, "valuta": b[1] if b else None})
    dagen_met_gebruik = max(1, len(per_dag))
    alles = sum(sum(w.values()) for w in per_deel.values()) or 1.0
    onderdelen = [{"onderdeel": d, "aanroepen": aanroepen_deel.get(d, 0),
                   "kosten": {k: round(v, 4) for k, v in w.items()},
                   "aandeel": round(100 * sum(w.values()) / alles, 1)}
                  for d, w in sorted(per_deel.items(), key=lambda x: -sum(x[1].values()))]
    return {
        "dagen": dagen, "prijzen_per": PRIJZEN_PER, "opslag": "register" if register.actief() else "geheugen",
        "regels": regels,
        "per_onderdeel": onderdelen,
        "per_dag": [{"dag": d, **{k: round(v, 4) for k, v in w.items()}} for d, w in sorted(per_dag.items())],
        "totaal": {k: round(v, 2) for k, v in totaal.items()},
        "per_maand": {k: round(v / dagen_met_gebruik * 21, 2) for k, v in totaal.items()},
        "onbekend": sorted(onbekend),
        "prijzen": tabel,
    }
