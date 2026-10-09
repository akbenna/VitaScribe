"""
VitaScribe Cloud API - Medisch Nederlands Vocabulaire

Postprocessing-laag voor transcriptcorrectie.
Corrigeert veelvoorkomende STT-fouten in medisch-Nederlandse termen.

Drie correctieniveaus:
1. Medicatienamen (meest foutgevoelig bij STT)
2. Medische termen en afkortingen
3. Lokale verwijslocaties en context

De woordenlijst groeit mee via de feedbackloop:
arts corrigeert transcript -> correctie wordt opgeslagen -> periodiek
worden nieuwe patronen aan deze lijst toegevoegd.

Compatible with Python 3.9+.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# ══════════════════════════════════════════════════════════════════════
# 1. MEDICATIENAMEN
# Top 200 huisartsgeneeskunde - veelvoorkomende STT-fouten links
# ══════════════════════════════════════════════════════════════════════

MEDICATION_CORRECTIONS: Dict[str, str] = {
    # --- Cardiovasculair ---
    "metaformien": "metformine",
    "metaformine": "metformine",
    "meta formine": "metformine",
    "metformin": "metformine",
    "amlodiepine": "amlodipine",
    "amlo die pine": "amlodipine",
    "amlodapine": "amlodipine",
    "lisinopril": "lisinopril",
    "lysino pril": "lisinopril",
    "losartan": "losartan",
    "lo sartan": "losartan",
    "atorvastatine": "atorvastatine",
    "atorva statine": "atorvastatine",
    "atorvast a tine": "atorvastatine",
    "ator vast atine": "atorvastatine",
    "simvastatine": "simvastatine",
    "simva statine": "simvastatine",
    "rosuvastatine": "rosuvastatine",
    "rosuva statine": "rosuvastatine",
    "carbasalaat calcium": "carbasalaatcalcium",
    "carbasalaat": "carbasalaatcalcium",
    "carbasa laat calcium": "carbasalaatcalcium",
    "ascal": "Ascal",
    "askal": "Ascal",
    "bisoprolol": "bisoprolol",
    "biso prolol": "bisoprolol",
    "metroprolol": "metoprolol",
    "metaprolol": "metoprolol",
    "meto prolol": "metoprolol",
    "hydrochloortiazide": "hydrochloorthiazide",
    "hydrochloorthiazide": "hydrochloorthiazide",
    "hydrochloor thiazide": "hydrochloorthiazide",
    "furosemide": "furosemide",
    "furo semide": "furosemide",
    "spironolacton": "spironolacton",
    "spirono lacton": "spironolacton",
    "acenocoumarol": "acenocoumarol",
    "aceno coumarol": "acenocoumarol",
    "clopidogrel": "clopidogrel",
    "clopi dogrel": "clopidogrel",
    "rivaroxaban": "rivaroxaban",
    "riva roxaban": "rivaroxaban",
    "apixaban": "apixaban",
    "api xaban": "apixaban",
    "dabigatran": "dabigatran",
    "dabi gatran": "dabigatran",

    # --- Pijnstilling / Analgetica ---
    "paracetamol": "paracetamol",
    "para cetamol": "paracetamol",
    "paracetemol": "paracetamol",
    "ibuprofen": "ibuprofen",
    "ibu profen": "ibuprofen",
    "naproxen": "naproxen",
    "nap roxen": "naproxen",
    "diclofenac": "diclofenac",
    "diclo fenac": "diclofenac",
    "tramadol": "tramadol",
    "trama dol": "tramadol",
    "oxycodon": "oxycodon",
    "oxy codon": "oxycodon",

    # --- Luchtwegen ---
    "salbutamol": "salbutamol",
    "sal butamol": "salbutamol",
    "salmeterol": "salmeterol",
    "formoterol": "formoterol",
    "fluticason": "fluticason",
    "flutica son": "fluticason",
    "budesonide": "budesonide",
    "bude sonide": "budesonide",
    "montelukast": "montelukast",
    "monte lukast": "montelukast",
    "tiotropium": "tiotropium",
    "tiotro pium": "tiotropium",
    "prednisolon": "prednisolon",
    "prednison": "prednison",
    "predni solon": "prednisolon",
    "dexamethason": "dexamethason",
    "dexa methason": "dexamethason",
    "amoxicilline": "amoxicilline",
    "amoxi cilline": "amoxicilline",
    "amoxiciline": "amoxicilline",
    "augmentin": "Augmentin",
    "augmentien": "Augmentin",
    "azitromycine": "azitromycine",
    "azitro mycine": "azitromycine",
    "doxycycline": "doxycycline",
    "doxy cycline": "doxycycline",
    "ciprofloxacine": "ciprofloxacine",
    "cipro floxacine": "ciprofloxacine",
    "nitrofurantoine": "nitrofurantoïne",
    "nitrofurantoïne": "nitrofurantoïne",
    "nitro furantoine": "nitrofurantoïne",
    "cotrimoxazol": "cotrimoxazol",
    "co trimoxazol": "cotrimoxazol",
    "flucloxacilline": "flucloxacilline",
    "fluclox acilline": "flucloxacilline",

    # --- Maag / Darm ---
    "omeprazol": "omeprazol",
    "ome prazol": "omeprazol",
    "pantoprazol": "pantoprazol",
    "panto prazol": "pantoprazol",
    "esomeprazol": "esomeprazol",
    "eso meprazol": "esomeprazol",
    "macrogol": "macrogol",
    "macro gol": "macrogol",
    "loperamide": "loperamide",
    "lopera mide": "loperamide",

    # --- Psychofarmaca ---
    "citalopram": "citalopram",
    "citalo pram": "citalopram",
    "sertraline": "sertraline",
    "ser traline": "sertraline",
    "escitalopram": "escitalopram",
    "paroxetine": "paroxetine",
    "paroxe tine": "paroxetine",
    "venlafaxine": "venlafaxine",
    "venla faxine": "venlafaxine",
    "mirtazapine": "mirtazapine",
    "mirta zapine": "mirtazapine",
    "amitriptyline": "amitriptyline",
    "ami triptyline": "amitriptyline",
    "diazepam": "diazepam",
    "dia zepam": "diazepam",
    "oxazepam": "oxazepam",
    "oxa zepam": "oxazepam",
    "lorazepam": "lorazepam",
    "lora zepam": "lorazepam",
    "temazepam": "temazepam",
    "tema zepam": "temazepam",
    "zolpidem": "zolpidem",
    "zol pidem": "zolpidem",
    "quetiapine": "quetiapine",
    "quetia pine": "quetiapine",
    "risperidon": "risperidon",
    "ris peridon": "risperidon",
    "methylfenidaat": "methylfenidaat",
    "methyl fenidaat": "methylfenidaat",
    "ritalin": "Ritalin",

    # --- Endocrien ---
    "levothyroxine": "levothyroxine",
    "levo thyroxine": "levothyroxine",
    "thyrax": "Thyrax",
    "insuline": "insuline",
    "glicla zide": "gliclazide",
    "gliclazide": "gliclazide",
    "empagliflozine": "empagliflozine",
    "empagli flozine": "empagliflozine",
    "semaglutide": "semaglutide",
    "sema glutide": "semaglutide",
    "ozempic": "Ozempic",
    "ozempik": "Ozempic",
    "liraglutide": "liraglutide",
    "lira glutide": "liraglutide",
    "dapagliflozine": "dapagliflozine",
    "dapa gliflozine": "dapagliflozine",

    # --- Dermatologie ---
    "betamethason": "betamethason",
    "beta methason": "betamethason",
    "triamcinolonacetonide": "triamcinolonacetonide",
    "triamcinolon": "triamcinolon",
    "hydrocortison": "hydrocortison",
    "hydro cortison": "hydrocortison",
    "permethrine": "permetrine",
    "permetrien": "permetrine",

    # --- Overig ---
    "allopurinol": "allopurinol",
    "allo purinol": "allopurinol",
    "colchicine": "colchicine",
    "col chicine": "colchicine",
    "vitamine d": "vitamine D",
    "vitamine D3": "vitamine D3",
    "calcium carbonaat": "calciumcarbonaat",
    "ferrofumaraat": "ferrofumaraat",
    "ferro fumaraat": "ferrofumaraat",
    "folic zuur": "foliumzuur",
    "folium zuur": "foliumzuur",
}


# ══════════════════════════════════════════════════════════════════════
# 2. MEDISCHE TERMEN EN AFKORTINGEN
# ══════════════════════════════════════════════════════════════════════

MEDICAL_TERM_CORRECTIONS: Dict[str, str] = {
    # --- Diagnosen / Aandoeningen ---
    "hyper tensie": "hypertensie",
    "diabetes mellitus": "diabetes mellitus",
    "diabetes melitus": "diabetes mellitus",
    "diabetes militus": "diabetes mellitus",
    "hypothyreoïdie": "hypothyreoïdie",
    "hypo thyreoïdie": "hypothyreoïdie",
    "hypothyreoidie": "hypothyreoïdie",
    "hyperthyreoïdie": "hyperthyreoïdie",
    "atriumfibrilleren": "atriumfibrilleren",
    "atrium fibrilleren": "atriumfibrilleren",
    "hartfalen": "hartfalen",
    "angina pectoris": "angina pectoris",
    "angina pektorus": "angina pectoris",
    "myocardinfarct": "myocardinfarct",
    "myocard infarct": "myocardinfarct",
    "cerebro vasculair accident": "cerebrovasculair accident",
    "cva": "CVA",
    "CVA": "CVA",
    "tia": "TIA",
    "TIA": "TIA",
    "copd": "COPD",
    "COPD": "COPD",
    "astma": "astma",
    "pneumonie": "pneumonie",
    "urine weg infectie": "urineweginfectie",
    "urineweginfectie": "urineweginfectie",
    "artrose": "artrose",
    "osteoporose": "osteoporose",
    "jicht": "jicht",
    "eczeem": "eczeem",
    "psoriasis": "psoriasis",
    "depressie": "depressie",
    "angst stoornis": "angststoornis",
    "paniek stoornis": "paniekstoornis",
    "slaap apneu": "slaapapneu",
    "gastro oesofageale reflux": "gastro-oesofageale reflux",

    # --- Lichamelijk onderzoek ---
    "bloeddruk": "bloeddruk",
    "bloed druk": "bloeddruk",
    "systolisch": "systolisch",
    "diastolisch": "diastolisch",
    "auscultatie": "auscultatie",
    "auskultatie": "auscultatie",
    "percussie": "percussie",
    "palpatie": "palpatie",
    "BMI": "BMI",
    "bmi": "BMI",

    # --- Onderzoek en verwijzing ---
    "echo cardiografie": "echocardiografie",
    "echocardiografie": "echocardiografie",
    "elektro cardiogram": "elektrocardiogram",
    "elektrocardiogram": "elektrocardiogram",
    "laboratorium": "laboratorium",
    "röntgen": "röntgen",
    "rontgen": "röntgen",
    "MRI": "MRI",
    "mri": "MRI",
    "CT scan": "CT-scan",
    "ct scan": "CT-scan",
    "CT-scan": "CT-scan",
    "echo": "echo",
    "spirometrie": "spirometrie",
    "spiro metrie": "spirometrie",

    # --- Medische afkortingen (als ze verkeerd worden herkend) ---
    "l.o.": "LO",
    "lo": "LO",
    "v.g.": "VG",
    "vg": "VG",
    "d.d.": "dd",
    "een d.d.": "1dd",
    "1 dd": "1dd",
    "2 dd": "2dd",
    "3 dd": "3dd",
    "een maal daags": "1dd",
    "twee maal daags": "2dd",
    "drie maal daags": "3dd",
    "milligram": "mg",
    "microgram": "mcg",
}


# ══════════════════════════════════════════════════════════════════════
# 3. ICPC-2 CODES (uitgesproken als tekst -> code)
# ══════════════════════════════════════════════════════════════════════

ICPC_SPOKEN_TO_CODE: Dict[str, str] = {
    "r 74": "R74",
    "r74": "R74",
    "k 86": "K86",
    "k86": "K86",
    "k 90": "K90",
    "k90": "K90",
    "t 90": "T90",
    "t90": "T90",
    "t 93": "T93",
    "t93": "T93",
    "k 74": "K74",
    "k74": "K74",
    "k 75": "K75",
    "k75": "K75",
    "k 76": "K76",
    "k76": "K76",
    "l 86": "L86",
    "l86": "L86",
    "u 71": "U71",
    "u71": "U71",
    "p 76": "P76",
    "p76": "P76",
    "p 03": "P03",
    "p03": "P03",
    "s 74": "S74",
    "s74": "S74",
    "d 12": "D12",
    "d12": "D12",
    "r 78": "R78",
    "r78": "R78",
    "r 96": "R96",
    "r96": "R96",
    "n 17": "N17",
    "n17": "N17",
}


# ══════════════════════════════════════════════════════════════════════
# 4. LOKALE VERWIJSLOCATIES (configureerbaar per praktijk)
# ══════════════════════════════════════════════════════════════════════

LOCAL_CORRECTIONS: Dict[str, str] = {
    # Ziekenhuizen Limburg
    "laurentius": "Laurentius Ziekenhuis",
    "zuyderland": "Zuyderland",
    "zuiderland": "Zuyderland",
    "zuyder land": "Zuyderland",
    "maastricht umc": "Maastricht UMC+",
    "mumc": "MUMC+",
    "MUMC": "MUMC+",
    "viasana": "ViaSana",
    "via sana": "ViaSana",

    # GGZ / Overig
    "mondriaan": "Mondriaan",
    "vincent van gogh": "Vincent van Gogh",

    # Huisartsenposten
    "huisartsen post": "huisartsenpost",
    "hap": "HAP",
}


# ══════════════════════════════════════════════════════════════════════
# 5. HOTWORDS VOOR VIBEVOICE-ASR (toekomstig)
# Dezelfde woordenlijst, maar dan als comma-separated string
# voor de hotwords parameter van VibeVoice-ASR
# ══════════════════════════════════════════════════════════════════════

def get_hotwords() -> str:
    """
    Genereer een hotwords-string voor VibeVoice-ASR.
    Bevat alle correcte termen uit de woordenlijst.
    """
    hotwords = set()

    # Alle correcte medicatienamen
    hotwords.update(MEDICATION_CORRECTIONS.values())

    # Alle correcte medische termen
    hotwords.update(MEDICAL_TERM_CORRECTIONS.values())

    # Lokale verwijslocaties
    hotwords.update(LOCAL_CORRECTIONS.values())

    # Sorteer voor consistentie
    return ",".join(sorted(hotwords))


# ══════════════════════════════════════════════════════════════════════
# 6. POSTPROCESSING ENGINE
# ══════════════════════════════════════════════════════════════════════

@dataclass
class CorrectionStats:
    """Statistieken van de correcties op een transcript."""
    total_corrections: int = 0
    medication_corrections: int = 0
    medical_term_corrections: int = 0
    icpc_corrections: int = 0
    local_corrections: int = 0
    corrections_applied: List[Tuple[str, str]] = field(default_factory=list)


def _apply_corrections(
    text: str,
    corrections: Dict[str, str],
    case_insensitive: bool = True,
) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Pas een set correcties toe op de tekst.
    Geeft de gecorrigeerde tekst en een lijst van gemaakte correcties terug.

    Sorteert op lengte (langste eerst) om gedeeltelijke matches te voorkomen.
    Gebruikt woordgrenzen om te voorkomen dat woorden in andere woorden worden
    gecorrigeerd (bijv. "lo" in "bloeddruk").
    """
    applied = []

    # Sorteer op lengte (langste eerst) om greedy matching te voorkomen
    sorted_corrections = sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True)

    for wrong, correct in sorted_corrections:
        if wrong == correct:
            continue

        # Gebruik woordgrenzen
        flags = re.IGNORECASE if case_insensitive else 0
        pattern = r"\b" + re.escape(wrong) + r"\b"

        matches = re.findall(pattern, text, flags=flags)
        if matches:
            text = re.sub(pattern, correct, text, flags=flags)
            for match in matches:
                applied.append((match, correct))

    return text, applied


def correct_transcript(text: str) -> Tuple[str, CorrectionStats]:
    """
    Pas alle correctielagen toe op een transcript.

    Returns:
        Tuple van (gecorrigeerd transcript, correctiestatistieken)
    """
    stats = CorrectionStats()

    if not text or not text.strip():
        return text, stats

    # Laag 1: Medicatienamen (hoogste prioriteit)
    text, med_corrections = _apply_corrections(text, MEDICATION_CORRECTIONS)
    stats.medication_corrections = len(med_corrections)
    stats.corrections_applied.extend(med_corrections)

    # Laag 2: Medische termen
    text, term_corrections = _apply_corrections(text, MEDICAL_TERM_CORRECTIONS)
    stats.medical_term_corrections = len(term_corrections)
    stats.corrections_applied.extend(term_corrections)

    # Laag 3: ICPC-codes
    text, icpc_corrections = _apply_corrections(text, ICPC_SPOKEN_TO_CODE)
    stats.icpc_corrections = len(icpc_corrections)
    stats.corrections_applied.extend(icpc_corrections)

    # Laag 4: Lokale verwijslocaties
    text, local_corrs = _apply_corrections(text, LOCAL_CORRECTIONS)
    stats.local_corrections = len(local_corrs)
    stats.corrections_applied.extend(local_corrs)

    stats.total_corrections = (
        stats.medication_corrections
        + stats.medical_term_corrections
        + stats.icpc_corrections
        + stats.local_corrections
    )

    return text, stats


# ══════════════════════════════════════════════════════════════════════
# 7. CUSTOM VOCABULARY MANAGEMENT
# Laden en opslaan van aanvullende correcties uit een JSON-bestand
# ══════════════════════════════════════════════════════════════════════

_custom_corrections: Dict[str, str] = {}
_custom_vocab_path: Optional[Path] = None


def load_custom_vocabulary(path: Path) -> int:
    """
    Laad aanvullende correcties uit een JSON-bestand.
    Format: {"verkeerd": "correct", ...}

    Returns: aantal geladen correcties
    """
    global _custom_corrections, _custom_vocab_path

    if not path.exists():
        logger.info("vocabulary.custom_not_found", path=str(path))
        return 0

    with open(path, "r", encoding="utf-8") as f:
        _custom_corrections = json.load(f)

    _custom_vocab_path = path
    logger.info(
        "vocabulary.custom_loaded",
        path=str(path),
        count=len(_custom_corrections),
    )
    return len(_custom_corrections)


def save_custom_vocabulary(path: Path = None) -> None:
    """Sla de huidige custom correcties op."""
    save_path = path or _custom_vocab_path
    if not save_path:
        return

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(_custom_corrections, f, ensure_ascii=False, indent=2)

    logger.info("vocabulary.custom_saved", path=str(save_path), count=len(_custom_corrections))


def add_custom_correction(wrong: str, correct: str) -> None:
    """Voeg een correctie toe aan de custom woordenlijst."""
    _custom_corrections[wrong.lower()] = correct
    logger.info("vocabulary.correction_added", wrong=wrong, correct=correct)


def correct_transcript_full(text: str) -> Tuple[str, CorrectionStats]:
    """
    Volledige correctie: ingebouwde + custom woordenlijst.
    Gebruik deze functie in de pipeline.
    """
    # Eerst de ingebouwde correcties
    text, stats = correct_transcript(text)

    # Dan de custom correcties
    if _custom_corrections:
        text, custom_corrs = _apply_corrections(text, _custom_corrections)
        stats.total_corrections += len(custom_corrs)
        stats.corrections_applied.extend(custom_corrs)

    return text, stats
