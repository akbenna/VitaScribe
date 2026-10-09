"""
VitaScribe - Evaluatie / Meetlat
================================

Lichtgewicht, dependency-vrije metrieken om kwaliteitswinst meetbaar te maken.
Zonder meetlat is elke upgrade een gok; met deze metrieken wordt elke wijziging
(hotwords, ander model, fine-tune) een gemeten, terugdraaibare beslissing.

Drie metrieken:
1. word_error_rate           - algemene transcriptiekwaliteit (WER)
2. medical_term_error_rate   - domeinspecifiek: hoe vaak gaat een medische term
                               of medicatienaam mis (weegt zwaarder dan een
                               fout lidwoord)
3. soep_edit_distance        - genormaliseerde afstand tussen gegenereerde en
                               door de arts goedgekeurde SOEP. Daalt naarmate
                               het systeem leert -> KPI voor de zelflerende laag.

Bewust pure stdlib zodat het overal draait (CI, lokaal, zonder GPU).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence


# ──────────────────────────────────────────────────────────────────────
# Normalisatie
# ──────────────────────────────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_text(text: str, *, keep_accents: bool = True) -> str:
    """Normaliseer tekst voor eerlijke vergelijking: lowercase, leestekens weg,
    witruimte genormaliseerd. Accenten blijven behouden (relevant in NL)."""
    if not text:
        return ""
    text = text.lower()
    if not keep_accents:
        text = "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    norm = normalize_text(text)
    return norm.split() if norm else []


# ──────────────────────────────────────────────────────────────────────
# Levenshtein (token- of teken-niveau)
# ──────────────────────────────────────────────────────────────────────

def _levenshtein(a: Sequence, b: Sequence) -> int:
    """Edit-afstand (insertions+deletions+substitutions) tussen twee sequenties."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(
                prev[j] + 1,        # deletion
                cur[j - 1] + 1,     # insertion
                prev[j - 1] + cost, # substitution
            ))
        prev = cur
    return prev[-1]


# ──────────────────────────────────────────────────────────────────────
# 1. Word Error Rate
# ──────────────────────────────────────────────────────────────────────

def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER = edit-afstand(woorden) / aantal referentiewoorden. 0.0 = perfect.

    Bij lege referentie: 0.0 als hypothese ook leeg is, anders 1.0.
    """
    ref = tokenize(reference)
    hyp = tokenize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


# ──────────────────────────────────────────────────────────────────────
# 2. Medische-term-foutmarge
# ──────────────────────────────────────────────────────────────────────

@dataclass
class TermResult:
    total_terms: int = 0          # aantal (voorkomens van) doeltermen in referentie
    correct: int = 0              # daarvan correct in hypothese
    missed_terms: List[str] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        if self.total_terms == 0:
            return 0.0
        return 1.0 - (self.correct / self.total_terms)

    @property
    def accuracy(self) -> float:
        return 1.0 - self.error_rate


def _term_phrase_present(term_tokens: List[str], hyp_tokens: List[str]) -> bool:
    """Komt de (mogelijk meerwoordige) term als aaneengesloten reeks voor?"""
    n = len(term_tokens)
    if n == 0:
        return False
    for i in range(len(hyp_tokens) - n + 1):
        if hyp_tokens[i:i + n] == term_tokens:
            return True
    return False


def medical_term_error_rate(
    reference: str,
    hypothesis: str,
    terms: Iterable[str],
) -> TermResult:
    """Meet hoe goed domeintermen (medicatie, diagnosen, ICPC) overkomen.

    Voor elke term die in de referentie voorkomt, controleer of die ook in de
    hypothese staat. Eén foute medicatienaam weegt hier net zo zwaar als elke
    andere - anders dan bij WER, waar lidwoorden meetellen.
    """
    ref_tokens = tokenize(reference)
    hyp_tokens = tokenize(hypothesis)
    res = TermResult()

    seen = set()
    for term in terms:
        norm = normalize_text(term)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        t_tokens = norm.split()
        if _term_phrase_present(t_tokens, ref_tokens):
            res.total_terms += 1
            if _term_phrase_present(t_tokens, hyp_tokens):
                res.correct += 1
            else:
                res.missed_terms.append(term)
    return res


def default_medical_terms() -> List[str]:
    """Verzamel doeltermen uit de gedeelde woordenlijst (best-effort import)."""
    try:
        from shared.vocabulary import (
            MEDICATION_CORRECTIONS,
            MEDICAL_TERM_CORRECTIONS,
            LOCAL_CORRECTIONS,
        )
    except Exception:
        return []
    terms = set()
    terms.update(MEDICATION_CORRECTIONS.values())
    terms.update(MEDICAL_TERM_CORRECTIONS.values())
    terms.update(LOCAL_CORRECTIONS.values())
    return sorted(t for t in terms if t)


# ──────────────────────────────────────────────────────────────────────
# 3. SOEP edit-distance (KPI zelflerende laag)
# ──────────────────────────────────────────────────────────────────────

_SOEP_FIELDS = ("S", "O", "E", "P")


@dataclass
class SoepEditResult:
    per_field: Dict[str, float] = field(default_factory=dict)
    overall: float = 0.0          # gewogen genormaliseerde teken-edit-afstand


def _normalized_char_distance(a: str, b: str) -> float:
    a_n = normalize_text(a)
    b_n = normalize_text(b)
    if not a_n and not b_n:
        return 0.0
    denom = max(len(a_n), len(b_n)) or 1
    return _levenshtein(a_n, b_n) / denom


def soep_edit_distance(generated: Dict[str, str], approved: Dict[str, str]) -> SoepEditResult:
    """Genormaliseerde afstand (0..1) tussen gegenereerde en goedgekeurde SOEP.

    0.0 = de arts hoefde niets te wijzigen (ideaal). Hoe lager, hoe beter het
    systeem de praktijkstijl raakt. Volg dit getal over de tijd als KPI.
    """
    res = SoepEditResult()
    total_len = 0
    weighted = 0.0
    for f in _SOEP_FIELDS:
        gen = (generated or {}).get(f, "") or ""
        app = (approved or {}).get(f, "") or ""
        d = _normalized_char_distance(gen, app)
        res.per_field[f] = round(d, 4)
        w = max(len(normalize_text(app)), 1)
        weighted += d * w
        total_len += w
    res.overall = round(weighted / total_len, 4) if total_len else 0.0
    return res
