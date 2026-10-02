"""
VitaScribe Cloud API - ICPC-controle (richting, geen officiële tabel)

Een kleine tabel van veelgebruikte ICPC-1-NL-codes met trefwoorden voor wat de
code betekent. De SOEP-test markeert een verslag waarvan de titel niet past bij
de code (een model gaf "L02 Pijn borstwand/ribben"; L02 is rugklachten).

Dit is GEEN vervanging van de officiële NHG-tabel: codes die hier niet staan,
worden niet beoordeeld. De tabel is door de arts te controleren
(GECONTROLEERD_OP en DOOR leeg = nog niet gecontroleerd). Vervang haar door de
NHG-tabel zodra die met licentie beschikbaar is.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

GECONTROLEERD_OP = ""
DOOR = ""

# code -> (korte omschrijving, trefwoorden waarvan er één in de titel moet staan)
TABEL: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "A03": ("koorts", ("koorts",)),
    "A04": ("moeheid/zwakte", ("moe", "zwakte", "vermoeid")),
    "D01": ("buikpijn/krampen algemeen", ("buik",)),
    "D73": ("gastro-enteritis", ("gastro", "enteritis", "darminfectie")),
    "H71": ("otitis media acuta", ("otitis", "middenoor")),
    "K74": ("angina pectoris", ("angina",)),
    "K77": ("hartfalen", ("hartfalen", "decompensatio")),
    "K78": ("atriumfibrilleren/-flutter", ("atrium", "boezem", "fibrill", "flutter")),
    "K86": ("hypertensie zonder orgaanbeschadiging", ("hypertensie", "bloeddruk")),
    "L01": ("nekklachten", ("nek",)),
    "L02": ("rugklachten", ("rug",)),
    "L03": ("lage rugklachten", ("rug", "lumbal")),
    "L04": ("borstkasklachten", ("borst", "thorax")),
    "L08": ("schouderklachten", ("schouder",)),
    "L15": ("knieklachten", ("knie",)),
    "L16": ("enkelklachten", ("enkel",)),
    "L77": ("verstuiking/distorsie enkel", ("enkel",)),
    "L86": ("lumbosacraal radiculair syndroom/hernia", ("hernia", "radiculair", "uitstraling")),
    "L90": ("artrose knie", ("artrose", "gonartrose", "knie")),
    "L92": ("schoudersyndroom", ("schouder",)),
    "N01": ("hoofdpijn", ("hoofdpijn",)),
    "N89": ("migraine", ("migraine",)),
    "P03": ("depressief gevoel", ("depressie", "somber")),
    "P06": ("slaapstoornis", ("slaap",)),
    "P74": ("angststoornis", ("angst",)),
    "P76": ("depressie", ("depressie", "depressieve")),
    "P78": ("overspanning/surmenage", ("overspann", "surmenage", "burn")),
    "R05": ("hoesten", ("hoest",)),
    "R74": ("acute infectie bovenste luchtwegen", ("luchtweg", "verkoud")),
    "R78": ("acute bronchitis/bronchiolitis", ("bronchit", "bronchiol")),
    "R81": ("pneumonie", ("pneumonie", "longontsteking")),
    "R95": ("COPD", ("copd", "emfyseem")),
    "R96": ("astma", ("astma",)),
    "S74": ("dermatomycose", ("mycose", "schimmel")),
    "T90": ("diabetes mellitus type 2", ("diabetes",)),
    "T93": ("vetstofwisselingsstoornis", ("vetstofwissel", "cholesterol", "lipid")),
    "U71": ("cystitis/urineweginfectie", ("cystitis", "urineweg", "blaasontsteking")),
}


def controleer(code: str, titel: str) -> Optional[str]:
    """None if the title fits the code (or the code is not in the table)."""
    kern = re.sub(r"\.\d+$", "", (code or "").strip().upper())
    if kern not in TABEL or not (titel or "").strip():
        return None
    omschrijving, woorden = TABEL[kern]
    laag = titel.lower()
    if any(w in laag for w in woorden):
        return None
    return f'ICPC {kern} is {omschrijving}; de titel "{titel}" past daar niet bij'


def controleer_delen(delen: List[dict]) -> List[str]:
    uit = []
    for d in delen:
        fout = controleer(str(d.get("icpc_code") or ""), str(d.get("icpc_titel") or ""))
        if fout:
            uit.append(fout)
    return uit
