"""
Diff-miner
==========

Extraheert kandidaat-correcties (fout -> goed) uit een origineel en een door de
arts gecorrigeerd transcript. Pure stdlib, volledig deterministisch en
unit-testbaar - geen DB, geen LLM.

Aanpak: woord-alignment via difflib.SequenceMatcher. We kijken uitsluitend naar
'replace'-operaties (vervangingen) van een korte woordreeks. Insertions en
deletions zijn te ruis-gevoelig (de arts schrapt of voegt inhoud toe) en leren
we bewust NIET als woordenlijstcorrectie.

Kwaliteitsfilters voorkomen vervuiling van de woordenlijst:
- alleen reeksen van 1..MAX_NGRAM woorden
- 'fout' en 'goed' moeten voldoende op elkaar lijken (waarschijnlijke ASR-
  verhoring, geen inhoudelijke herschrijving)
- geen cijfers (doseringen/codes laten we met rust)
- geen lege/stopwoord-only wijzigingen
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Tuple

# Maximaal aantal woorden in een gemijnde correctie (kort houden = veilig)
MAX_NGRAM = 3
# Minimale tekengelijkenis tussen fout en goed (0..1). Hoog genoeg om
# inhoudelijke herschrijvingen ("griep" -> "een flinke verkoudheid") uit te
# sluiten, laag genoeg om verhoringen ("metaformien" -> "metformine") te vangen.
MIN_SIMILARITY = 0.5
# Minimale lengte van een term-token (skip "de", "en", losse letters)
MIN_TOKEN_LEN = 3

_WORD_RE = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)
_HAS_DIGIT = re.compile(r"\d")
# Toegestane teken in een term: letters (incl. accenten) en koppelteken
_TERM_OK = re.compile(r"^[a-zà-ÿ][a-zà-ÿ\-]*$", flags=re.IGNORECASE)

# Stopwoorden die we nooit als (deel van) een correctie willen leren
_STOPWORDS = {
    "de", "het", "een", "en", "of", "maar", "want", "dus", "die", "dat",
    "is", "was", "zijn", "wordt", "met", "voor", "van", "op", "in", "te",
    "ik", "hij", "zij", "ze", "we", "wij", "u", "je", "jij",
}


@dataclass(frozen=True)
class CandidateCorrection:
    wrong: str   # genormaliseerd (lowercase) - sleutel voor de woordenlijst
    correct: str # behoudt de schrijfwijze uit het gecorrigeerde transcript


def _tokenize(text: str) -> List[str]:
    """Splits in woord- en interpunctietokens (interpunctie wordt later genegeerd)."""
    return _WORD_RE.findall(text or "")


def _is_wordish(tok: str) -> bool:
    return bool(tok) and tok.isalnum() or "-" in tok


def _valid_phrase(tokens: List[str]) -> bool:
    """Is dit een schone, leerbare woordreeks?"""
    if not tokens or len(tokens) > MAX_NGRAM:
        return False
    for t in tokens:
        if _HAS_DIGIT.search(t):
            return False
        if not _TERM_OK.match(t):
            return False
        if len(t) < MIN_TOKEN_LEN:
            return False
    # Niet uitsluitend stopwoorden
    if all(t.lower() in _STOPWORDS for t in tokens):
        return False
    return True


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def mine_corrections(original: str, corrected: str) -> List[CandidateCorrection]:
    """Geef de kandidaat-correcties (fout -> goed) uit één feedbackpaar.

    Retourneert een lijst zonder duplicaten binnen dit ene paar.
    """
    orig_tokens = [t for t in _tokenize(original)]
    corr_tokens = [t for t in _tokenize(corrected)]
    if not orig_tokens or not corr_tokens:
        return []

    # Alleen 'echte' woorden meenemen in de alignment (interpunctie weg)
    orig_words = [t for t in orig_tokens if t.isalnum() or "-" in t]
    corr_words = [t for t in corr_tokens if t.isalnum() or "-" in t]

    sm = SequenceMatcher(None, [w.lower() for w in orig_words], [w.lower() for w in corr_words])
    results: List[CandidateCorrection] = []
    seen = set()

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        wrong_tokens = orig_words[i1:i2]
        correct_tokens = corr_words[j1:j2]

        if not _valid_phrase(wrong_tokens) or not _valid_phrase(correct_tokens):
            continue

        wrong = " ".join(wrong_tokens)
        correct = " ".join(correct_tokens)

        if wrong.lower() == correct.lower():
            continue
        if _similar(wrong, correct) < MIN_SIMILARITY:
            continue

        key = (wrong.lower(), correct)
        if key in seen:
            continue
        seen.add(key)
        results.append(CandidateCorrection(wrong=wrong.lower(), correct=correct))

    return results
