"""
VitaScribe Cloud API - Vraagsuggesties tijdens het consult

Luistert mee met het live consult (consult_live) en stelt de arts af en toe
een paar korte vragen voor die bij de besproken klacht horen en nog niet
gesteld zijn ("koorts?", "uitstraling?", "suïcidegedachten?"). De arts ziet
ze als chips in het zijpaneel en beslist zelf.

Dit is klinische beslissingsondersteuning (MDR regel 11). Het staat daarom
alleen aan als:
  - de server het toestaat: CLINICAL_DECISION_SUPPORT=true (data_policy), en
  - de arts het in de extensie heeft aangezet (auth-bericht "vraagsuggesties").
Een verkochte server zonder die instelling doet dus nooit suggesties.

Kosten en rust: hooguit eens per SUGGESTIE_INTERVAL_SECS, alleen als er
genoeg nieuwe tekst is, nooit twee tegelijk, en niet meer na "Nadicteren"
(de patiënt is dan weg). Het snelle model (quality=False) houdt het goedkoop
en de wachttijd kort. Het transcript gaat naar hetzelfde taalmodel als de
rest van de patiëntgegevens (data_policy.phi_llm_provider).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog

from . import audit, data_policy, llm_service, stt_service

logger = structlog.get_logger()

SUGGESTIE_INTERVAL_SECS = 30.0
MIN_WOORDEN_EERSTE = 25        # eerst moet er een klacht te horen zijn
MIN_NIEUWE_WOORDEN = 15
MAX_VRAGEN = 4
MAX_TRANSCRIPT_TEKENS = 6000   # het laatste stuk van het gesprek
SUGGESTIE_MAX_TOKENS = 450   # vier vragen met elk een korte "waarom"

SYSTEM_PROMPT = """\
Je luistert als ervaren Nederlandse huisarts mee met een lopend consult. \
Je helpt de arts NIETS te vergeten bij het uitvragen.

TAAK
- Bepaal de hoofdklacht(en) waarover het gesprek gaat.
- Geef hooguit 4 vragen die voor deze klacht essentieel zijn (NHG-standaard: \
  kernanamnese en alarmsymptomen) en die in het gesprek NOG NIET gesteld of \
  beantwoord zijn. Het belangrijkste eerst; alarmsymptomen voorrang.
- Elke vraag 1 tot 4 woorden, als steekwoord met vraagteken: "koorts?", \
  "uitstraling been?", "bloed bij ontlasting?", "suïcidegedachten?".
- "alarm": true bij een alarmsymptoom of rode vlag; anders false.
- "waarom": waarom de vraag ertoe doet, hooguit 10 woorden: welke \
  aandoening of rode vlag ze helpt aantonen of uitsluiten, of wat ze \
  bepaalt voor urgentie of beleid. Bijv. "uitsluiten meningitis", \
  "radiculair: HNP", "bepaalt of antibiotica zinvol is".

GRENZEN
- Alleen vragen, geen diagnoses, geen onderzoek of behandeladvies. Alleen \
  "waarom" noemt de aandoening waar een vraag bij helpt, als achtergrond.
- Is al gevraagd of verteld (ook ontkennend), dan NIET voorstellen.
- Is er nog geen klacht te horen (begroeting, small talk): lege lijst.
- Sprekerlabels zeggen niet wie de arts is; leid dat af uit de inhoud.

ANTWOORD als JSON: {"klacht": "...", "vragen": [{"tekst": "...", "alarm": false, "waarom": "..."}]}"""

USER_TEMPLATE = """\
GESPREK TOT NU TOE:
{gesprek}"""

# Dicteren houdt de sprekers niet uit elkaar: het kan een dictaat van de arts
# zijn of een gesprek dat met de dicteermicrofoon is opgenomen.
DICTAAT_TEMPLATE = """\
Let op: tekst uit de dicteermicrofoon, zonder sprekerscheiding. Het kan een \
dictaat van de arts over de patiënt zijn, of een opgenomen gesprek. Stel \
alleen vragen voor over wat nog niet genoemd of beantwoord is.

TEKST TOT NU TOE:
{gesprek}"""

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "klacht": {"type": "string"},
        "vragen": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"tekst": {"type": "string"}, "alarm": {"type": "boolean"},
                               "waarom": {"type": "string"}},
                "required": ["tekst", "alarm", "waarom"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["klacht", "vragen"],
    "additionalProperties": False,
}


def toegestaan(auth: Dict[str, Any]) -> bool:
    """Server staat het toe én de arts zette het aan."""
    return data_policy.clinical_decision_support() and auth.get("vraagsuggesties") is True


def schoon(data: Dict[str, Any]) -> Dict[str, Any]:
    """Modeluitvoer -> {klacht, vragen[{tekst, alarm}]}, kort en zonder dubbelen."""
    vragen: List[Dict[str, Any]] = []
    gezien = set()
    for v in data.get("vragen") or []:
        if isinstance(v, str):
            v = {"tekst": v, "alarm": False}
        if not isinstance(v, dict):
            continue
        tekst = " ".join(str(v.get("tekst") or "").split())[:40]
        if not tekst or tekst.lower() in gezien:
            continue
        gezien.add(tekst.lower())
        vragen.append({"tekst": tekst, "alarm": bool(v.get("alarm")),
                       "waarom": " ".join(str(v.get("waarom") or "").split())[:100]})
        if len(vragen) >= MAX_VRAGEN:
            break
    return {"klacht": " ".join(str(data.get("klacht") or "").split())[:60], "vragen": vragen}


async def maak_suggesties(gesprek_tekst: str, provider: Optional[str] = None,
                          bron: str = "consult") -> Dict[str, Any]:
    from .pipeline import _parse_json_response

    sjabloon = DICTAAT_TEMPLATE if bron == "dictaat" else USER_TEMPLATE
    from . import kosten
    with kosten.als("meedenken"):   # the cost breakdown: questions during the consult
        raw = await llm_service.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=sjabloon.format(gesprek=gesprek_tekst[-MAX_TRANSCRIPT_TEKENS:]),
            provider=data_policy.phi_llm_provider(provider),
            json_mode=True,
            max_tokens=SUGGESTIE_MAX_TOKENS,
            json_schema=JSON_SCHEMA,
        )
    return schoon(_parse_json_response(raw))


class Meedenker:
    """Beslist wanneer er nieuwe suggesties komen, en haalt ze op de achtergrond."""

    def __init__(self, zend: Callable[[Dict[str, Any]], Awaitable[None]], gebruiker: str = "",
                 provider: Optional[str] = None,
                 maak: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
                 klok: Callable[[], float] = time.monotonic,
                 bron: str = "consult") -> None:
        self.zend = zend
        self.bron = bron   # "consult" (sprekers) of "dictaat" (platte tekst)
        self.gebruiker = gebruiker
        self.provider = provider
        self.maak = maak
        self.klok = klok
        self.laatste_tijd: Optional[float] = None
        self.laatste_woorden = 0
        self.laatste: Optional[Dict[str, Any]] = None
        self.taak: Optional[asyncio.Task] = None
        self.aantal = 0

    @staticmethod
    def woorden(gesprek: Any) -> int:
        return sum(len(s.text.split()) for s in gesprek.segmenten if s.speaker != stt_service.NADICTAAT)

    def moet_nu(self, gesprek: Any) -> bool:
        if gesprek.nadictaat_vanaf is not None:
            return False
        return self._moet(self.woorden(gesprek))

    def _moet(self, woorden: int) -> bool:
        if self.taak is not None and not self.taak.done():
            return False
        if self.laatste_tijd is None:
            return woorden >= MIN_WOORDEN_EERSTE
        return (self.klok() - self.laatste_tijd >= SUGGESTIE_INTERVAL_SECS
                and woorden - self.laatste_woorden >= MIN_NIEUWE_WOORDEN)

    def misschien(self, gesprek: Any) -> None:
        """Na elk nieuw stuk tekst aanroepen; start zo nodig een ronde."""
        if not self.moet_nu(gesprek):
            return
        self.laatste_tijd = self.klok()
        self.laatste_woorden = self.woorden(gesprek)
        tekst = stt_service.met_sprekers(gesprek.transcript())
        self.taak = asyncio.create_task(self._ronde(tekst))

    def misschien_tekst(self, tekst: str) -> None:
        """Voor dicteren: dezelfde regels, op platte tekst zonder sprekers."""
        woorden = len(tekst.split())
        if not self._moet(woorden):
            return
        self.laatste_tijd = self.klok()
        self.laatste_woorden = woorden
        self.taak = asyncio.create_task(self._ronde(tekst))

    async def _ronde(self, tekst: str) -> None:
        try:
            if self.maak is not None:
                uit = await self.maak(tekst, self.provider)
            else:
                uit = await maak_suggesties(tekst, self.provider, bron=self.bron)
        except Exception as exc:   # een suggestie mag het consult nooit hinderen
            logger.warning("vraagsuggesties.mislukt", error=str(exc))
            return
        if uit == self.laatste:
            return
        self.laatste = uit
        self.aantal += 1
        await self.zend({"type": "suggesties", **uit})

    def stop(self) -> None:
        if self.taak is not None and not self.taak.done():
            self.taak.cancel()
        if self.aantal:
            audit.log_event(self.gebruiker, f"{'dictation' if self.bron == 'dictaat' else 'consult'}.vraagsuggesties",
                            rondes=self.aantal)
