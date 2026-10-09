"""
Diarisatie-alignment (woord-niveau)
===================================

Lost het kernprobleem van segment-niveau diarisatie op: één Whisper-segment kan
twee sprekers overspannen (arts stelt vraag, patiënt antwoordt binnen hetzelfde
segment), waardoor de S/O-toewijzing in de SOEP vervuilt.

Aanpak: wijs elk WOORD toe aan de spreker met de grootste temporele overlap,
en hergroepeer aaneengesloten woorden van dezelfde spreker tot nette segmenten.

Pure stdlib, geen pyannote/torch - volledig deterministisch en unit-testbaar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


@dataclass
class SpeakerSegment:
    speaker: str
    start: float
    end: float
    words: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.words).strip()


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_word_speaker(word: Word, turns: List[SpeakerTurn]) -> Optional[str]:
    """Bepaal de spreker van één woord via maximale overlap; valt terug op de
    dichtstbijzijnde turn (op middelpunt) als er geen overlap is."""
    if not turns:
        return None

    best_speaker = None
    best_overlap = 0.0
    for t in turns:
        ov = _overlap(word.start, word.end, t.start, t.end)
        if ov > best_overlap:
            best_overlap = ov
            best_speaker = t.speaker

    if best_speaker is not None:
        return best_speaker

    # Geen overlap (bv. korte stilte-grens): kies dichtstbijzijnde turn
    midpoint = (word.start + word.end) / 2.0
    nearest = min(
        turns,
        key=lambda t: abs(midpoint - (t.start + t.end) / 2.0),
    )
    return nearest.speaker


def group_words_by_speaker(
    words: List[Word], turns: List[SpeakerTurn]
) -> List[SpeakerSegment]:
    """Wijs woorden toe aan sprekers en groepeer aaneengesloten gelijke sprekers
    tot segmenten. Behoudt de woordvolgorde."""
    segments: List[SpeakerSegment] = []
    current: Optional[SpeakerSegment] = None

    for w in words:
        text = (w.text or "").strip()
        if not text:
            continue
        spk = assign_word_speaker(w, turns) or "onbekend"
        if current is None or current.speaker != spk:
            current = SpeakerSegment(speaker=spk, start=w.start, end=w.end, words=[text])
            segments.append(current)
        else:
            current.words.append(text)
            current.end = w.end

    return segments


def aggregate_speaker_text(segments: List[SpeakerSegment]) -> Dict[str, str]:
    """Verzamel alle tekst per spreker (input voor rolherkenning)."""
    buckets: Dict[str, List[str]] = {}
    for seg in segments:
        buckets.setdefault(seg.speaker, []).append(seg.text)
    return {spk: " ".join(parts).strip() for spk, parts in buckets.items()}
