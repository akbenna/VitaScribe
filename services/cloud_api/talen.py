"""
VitaScribe Cloud API - Taal van het consult

De arts kiest per consult in welke taal het gesprek gaat. Nederlands is de
standaard. "Meertalig" gebruikt Deepgram Nova-3 met language=multi: dat volgt
wisselingen tussen Nederlands, Engels, Frans, Duits, Spaans, Italiaans,
Portugees, Russisch, Hindi en Japans binnen één gesprek. Turks, Pools en
Oekraïens hebben een eigen Nova-3-model; dat verstaat alleen die taal, dus
alleen zinvol als (vrijwel) het hele gesprek in die taal gaat, bijvoorbeeld
met een tolk die voor de arts vertaalt.

De SOEP-regel is altijd Nederlands; het taalmodel vertaalt en noemt in S in
welke taal het consult ging.

Keyterms (medische woorden en medicijnnamen) zijn Nederlands; die gaan alleen
mee bij Nederlands, Engels en meertalig.
"""

from __future__ import annotations

from typing import Dict, NamedTuple, Optional


class Taal(NamedTuple):
    code: str        # wat de extensie stuurt
    deepgram: str    # Deepgram "language"
    naam: str        # voor de arts en het taalmodel
    keyterms: bool


TALEN: Dict[str, Taal] = {
    "nl": Taal("nl", "nl", "Nederlands", True),
    "multi": Taal("multi", "multi", "meertalig (Nederlands met Engels, Frans, Duits, Spaans of andere)", True),
    "en": Taal("en", "en", "Engels", True),
    "tr": Taal("tr", "tr", "Turks", False),
    "pl": Taal("pl", "pl", "Pools", False),
    "uk": Taal("uk", "uk", "Oekraïens", False),
}

STANDAARD = "nl"


def kies(code: Optional[str]) -> Taal:
    """Een onbekende of lege keuze wordt Nederlands."""
    return TALEN.get(str(code or "").strip().lower(), TALEN[STANDAARD])


def prompt_regel(taal: Taal) -> str:
    """Regel voor het taalmodel; leeg bij Nederlands."""
    if taal.code == STANDAARD:
        return ""
    return (f"TAAL VAN HET GESPREK (ingesteld door de arts): {taal.naam}. Schrijf de SOEP in het "
            "Nederlands en noem in S in welke taal het consult ging en of er een tolk bij was.\n\n")
