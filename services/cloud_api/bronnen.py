"""
VitaScribe Cloud API - Bronnen bij de SOEP

Bij elke zin van het verslag zoekt VitaScribe de passage in het gesprek waar
hij vandaan komt, zodat de arts met één klik ziet waarop een regel berust.
Dat is de positieve kant van de controleronde: die wijst aan wat het gesprek
níét onderbouwt, dit laat zien wat het wel onderbouwt.

Bewust zonder taalmodel:
- er gaat geen extra gegeven de deur uit, in beide modi;
- het kost niets en duurt milliseconden;
- een bron kan niet verzonnen zijn: elke bron is letterlijk tekst uit het
  transcript, en de zoeker kan alleen aanwijzen, niet schrijven.

Hoe: het verslag en het gesprek worden in zinnen geknipt en tot inhoudswoorden
teruggebracht (stopwoorden eruit, telwoorden als cijfer, gangbare
afkortingen uitgeschreven). Een woord uit het verslag telt als gevonden als
het letterlijk in een gesprekszin staat, als stam ("hoest" en "hoesten"), of
als samenstelling ("keelpijn" uit "pijn in mijn keel"). Zeldzame woorden
wegen zwaarder dan woorden die overal in het gesprek staan. De beste zin, of
twee opeenvolgende zinnen samen, is de bron.

Wat niet gevonden wordt, krijgt geen bron. Dat is geen fout: een conclusie of
samenvatting van de arts staat vaak niet letterlijk in het gesprek. De arts
ziet het verschil en beslist.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

SOEP_VELDEN = ("s", "o", "e", "p")
DREMPEL = 0.6           # deel van het gewicht dat teruggevonden moet zijn voor "bron"
DEELS = 0.3             # daaronder: geen bron
TWEEDE_WINST = 0.15     # een tweede gesprekszin alleen als die duidelijk meer dekt
MAX_BRON = 300          # tekens bron per zin, voor het paneel
MAX_ZINNEN = 200        # zinnen in het verslag (ruim een lang consult)

_STOP = set("""
de het een en of van in op te is dat die met voor aan bij als er ook om tot uit naar dan maar nog wel al
zijn was waren is ben bent heeft hebben heb had hadden wordt worden werd kan kunnen kon zal zou moet
ik u je jij jou hij zij ze we wij mij me mijn uw zijn haar hun ons onze jullie hem
zo dit deze daar hier wat wie hoe waar nu toen dus want omdat even echt heel erg gewoon eigenlijk
ja nee oke oké hè he hm uh eh zeg zegt zegje gaat gaan ga doe doet doen mag
patient patiënt pt pat dhr mw mevr meneer mevrouw sinds sedert per
""".split())

# Telwoorden in het gesprek, cijfers in het verslag.
_GETAL = {"twee": "2", "drie": "3", "vier": "4", "vijf": "5", "zes": "6", "zeven": "7", "acht": "8",
          "negen": "9", "tien": "10", "elf": "11", "twaalf": "12", "dertien": "13", "veertien": "14",
          "vijftien": "15", "twintig": "20", "dertig": "30", "veertig": "40", "vijftig": "50",
          "zestig": "60", "honderd": "100", "anderhalf": "1,5", "één": "1"}

# Afkortingen in een huisartsverslag, uitgeschreven zoals ze gezegd worden.
_AFKORTING = {"li": "links", "re": "rechts", "bdz": "beiderzijds", "rr": "bloeddruk", "bd": "bloeddruk",
              "pcm": "paracetamol", "ibu": "ibuprofen", "wk": "week", "wkn": "weken", "mnd": "maand",
              "mndn": "maanden", "dg": "dag", "dgn": "dagen", "jr": "jaar", "temp": "temperatuur",
              "ctrl": "controle", "zn": "nodig", "dd": "dag", "x": "keer", "afw": "afwijkingen",
              "bijz": "bijzonderheden", "vg": "voorgeschiedenis", "med": "medicatie", "ab": "antibiotica"}

# Report language that is never said literally; never reported as missing.
_LIJM = set("""
geleden direct lukt lukken eerder daarna nadien vanaf ongeveer circa sindsdien wisselend momenteel
thans recent inmiddels beleid uitleg advies gegeven besproken afgesproken klachten
""".split())

# A medical term in the report for what the patient said in lay words. Only
# for finding the source; the report itself is never changed.
_VAKTERM = {"distorsie": "verzwikking", "inversietrauma": "verzwikking", "tonsillitis": "keelontsteking",
            "pharyngitis": "keelontsteking", "faryngitis": "keelontsteking", "cystitis": "blaasontsteking",
            "cephalgie": "hoofdpijn", "cefalgie": "hoofdpijn", "dyspnoe": "benauwd", "pyrosis": "maagzuur",
            "obstipatie": "verstopping", "nausea": "misselijk", "vertigo": "duizelig", "febris": "koorts",
            "tussis": "hoest", "lumbago": "rugpijn", "lumbalgie": "rugpijn", "myalgie": "spierpijn",
            "artralgie": "gewrichtspijn", "dysurie": "plassen", "pollakisurie": "plassen", "rhinitis": "neus",
            "otalgie": "oorpijn", "malaise": "moe", "vermoeidheid": "moe", "palpitaties": "hartkloppingen",
            "syncope": "flauwgevallen", "insomnia": "slapen", "insomnie": "slapen"}

_ICPC = re.compile(r"^[a-z]\d{2}$")          # (R76) in E: staat nooit in het gesprek
_WOORD = re.compile(r"[a-zà-ÿ0-9]+(?:[.,]\d+)?")
_SPREKER = re.compile(r"^\s*(Spreker \d+|Nadictaat arts)\s*:\s*", re.IGNORECASE)
_ZINEINDE = re.compile(r"(?<=[.!?…])\s+|\n+")


def _woorden_met_vorm(tekst: str) -> List[Tuple[str, str]]:
    """(normalised, as written) per content word."""
    uit = []
    for vorm in _WOORD.findall((tekst or "").lower()):
        w = _AFKORTING.get(vorm, vorm)
        w = _VAKTERM.get(w, _GETAL.get(w, w))
        if w in _STOP or w in _LIJM or _ICPC.match(w) or (len(w) < 2 and not w.isdigit()):
            continue
        uit.append((w, vorm))
    return uit


def _woorden(tekst: str) -> List[str]:
    return [w for w, _ in _woorden_met_vorm(tekst)]


def gesprekszinnen(transcript: str) -> List[Dict[str, str]]:
    """The conversation in sentences, each with its speaker label (if any)."""
    zinnen: List[Dict[str, str]] = []
    for regel in (transcript or "").splitlines():
        if not regel.strip():
            continue
        m = _SPREKER.match(regel)
        spreker = m.group(1) if m else ""
        inhoud = regel[m.end():] if m else regel
        for zin in _ZINEINDE.split(inhoud):
            zin = zin.strip()
            if zin and _woorden(zin):
                zinnen.append({"spreker": spreker, "tekst": zin})
    return zinnen


def verslagzinnen(tekst: str) -> List[str]:
    """The report field in sentences or short fragments (SOEP style: ';' and '.')."""
    return [z.strip() for z in re.split(r"(?<=[.!?;])\s+|\n+", tekst or "") if z.strip()]


def _gevonden(w: str, gesprek: Sequence[str], gezet: set) -> float:
    """1 literally, 0.8 as stem or compound, else 0."""
    if w in gezet:
        return 1.0
    if w.isdigit() or len(w) < 4:
        return 0.0
    for g in gesprek:
        if len(g) >= 4 and len(w) >= 5 and len(g) >= 5 and w[:5] == g[:5]:
            return 0.8                                   # hoest / hoesten, rugpijn / rugpijnen
        if len(g) >= 4 and (g in w or w in g):
            if len(g) >= 4 and len(w) >= 4:
                # pijn in keelpijn: part of a compound counts if it is a real part.
                deel, geheel = (g, w) if len(g) < len(w) else (w, g)
                if geheel.startswith(deel) or geheel.endswith(deel):
                    return 0.8
    # keelpijn from "pijn in mijn keel": two words of the sentence together form it.
    if len(w) >= 7:
        kop = [g for g in gezet if len(g) >= 3 and w.startswith(g)]
        staart = [g for g in gezet if len(g) >= 3 and w.endswith(g)]
        if any(len(a) + len(b) >= len(w) - 1 for a in kop for b in staart if a != b or len(a) * 2 >= len(w)):
            return 0.8
    return 0.0


def _gewichten(zinnen: List[List[str]]) -> Dict[str, float]:
    n = len(zinnen) or 1
    df: Dict[str, int] = {}
    for z in zinnen:
        for w in set(z):
            df[w] = df.get(w, 0) + 1
    return {w: math.log((n + 1) / (d + 1)) + 1.0 for w, d in df.items()}


def _score(woorden: List[str], gesprek: List[str], gewicht: Dict[str, float], standaard: float) -> float:
    if not woorden:
        return 0.0
    gezet = set(gesprek)
    totaal = sum(gewicht.get(w, standaard) for w in woorden)
    raak = sum(gewicht.get(w, standaard) * _gevonden(w, gesprek, gezet) for w in woorden)
    return raak / totaal if totaal else 0.0


def zoek_bron(zin: str, zinnen: List[Dict[str, str]], woorden_per_zin: List[List[str]],
              gewicht: Dict[str, float], alle: Optional[List[str]] = None) -> Dict:
    """The sources for one report sentence: the conversation sentence that
    covers it best, plus at most one more for what the first does not cover
    (a SOEP sentence often joins two moments of the conversation).

    Returns {status, score, bronnen, ontbreekt}:
      bron   clearly in the conversation;
      deels  partly; or a word is in no sentence of the conversation at all;
      geen   not found.
    ontbreekt: words as written in the report that occur nowhere in the
    conversation (a dose, a side, a finding nobody said); report language
    such as "geleden" does not count at all (_LIJM)."""
    met_vorm = _woorden_met_vorm(zin)
    woorden = [w for w, _ in met_vorm]
    if alle is None:
        alle = [w for z in woorden_per_zin for w in z]
    alle_set = set(alle)
    ontbreekt = list(dict.fromkeys(vorm for w, vorm in met_vorm
                                   if _gevonden(w, alle, alle_set) == 0.0))
    leeg = {"status": "geen", "score": 0.0, "bronnen": [], "ontbreekt": ontbreekt}
    if not woorden or not zinnen:
        return leeg
    standaard = max(gewicht.values(), default=1.0)      # a word nowhere in the conversation weighs most
    totaal = sum(gewicht.get(w, standaard) for w in woorden)
    treffers = []      # per conversation sentence: how well each report word is found there
    for g in woorden_per_zin:
        gezet = set(g)
        treffers.append([_gevonden(w, g, gezet) for w in woorden])

    def dekking(rij: List[float]) -> float:
        return sum(gewicht.get(w, standaard) * r for w, r in zip(woorden, rij)) / totaal if totaal else 0.0

    eerste = max(range(len(treffers)), key=lambda i: (dekking(treffers[i]), -i))
    gekozen, rij = [eerste], list(treffers[eerste])
    if dekking(rij) < 1.0:
        tweede = max(range(len(treffers)),
                     key=lambda i: (dekking([max(a, b) for a, b in zip(rij, treffers[i])]), -abs(i - eerste)))
        samen = [max(a, b) for a, b in zip(rij, treffers[tweede])]
        if tweede != eerste and dekking(samen) >= dekking(rij) + TWEEDE_WINST:
            gekozen, rij = sorted([eerste, tweede]), samen
    score = round(dekking(rij), 2)
    if score < DEELS:
        return dict(leeg, score=score)
    bronnen = []
    for i in gekozen:
        tekst = zinnen[i]["tekst"]
        if len(tekst) > MAX_BRON:
            tekst = tekst[:MAX_BRON - 1].rstrip() + "…"
        bronnen.append({"spreker": zinnen[i]["spreker"], "tekst": tekst})
    status = "bron" if score >= DREMPEL and not ontbreekt else "deels"
    return {"status": status, "score": score, "bronnen": bronnen, "ontbreekt": ontbreekt}


def bronnen_bij_soep(transcript: str, delen: Sequence[Dict[str, str]]) -> List[Dict]:
    """Per report sentence (per part and field): {probleem, veld, zin, status,
    score, bronnen, ontbreekt}; see zoek_bron."""
    zinnen = gesprekszinnen(transcript)
    if not zinnen:
        return []
    per_zin = [_woorden(z["tekst"]) for z in zinnen]
    gewicht = _gewichten(per_zin)
    alle = list(dict.fromkeys(w for z in per_zin for w in z))
    uit: List[Dict] = []
    for nr, deel in enumerate(delen):
        for veld in SOEP_VELDEN:
            for zin in verslagzinnen(str(deel.get(veld) or "")):
                if len(uit) >= MAX_ZINNEN:
                    return uit
                if not _woorden(zin):
                    continue
                uit.append(dict(zoek_bron(zin, zinnen, per_zin, gewicht, alle), probleem=nr, veld=veld, zin=zin))
    return uit
