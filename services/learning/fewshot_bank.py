"""
Few-shot-bank (Fase 2, niveau 2)
================================

De tweede zelflerende laag: leer de SOEP-stijl van DEZE praktijk uit eerder
door de arts goedgekeurde SOEP's, en bied bij een nieuw consult de meest
gelijkende voorbeelden aan het LLM aan (dynamische few-shot).

Anders dan niveau 1 (woordenlijst → beter verstaan/corrigeren) tilt dit de
*formulering* op: abstractieniveau, afkortingsvoorkeuren, ICPC-gewoonten.

Privacy: voorbeelden bevatten klinische inhoud. Ze staan lokaal en
gepseudonimiseerd in een aparte bank (zelfde bewaarregime als consulten).
`scrub_pii` is een defense-in-depth-laag bovenop de reeds gepseudonimiseerde
brondata.

Bewust dependency-vrij (stdlib): retrieval via gewogen token-gelijkenis, geen
embeddings/externe modellen - past bij de lokale, auditeerbare opzet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_WORD_RE = re.compile(r"[a-zà-ÿ0-9]+", flags=re.IGNORECASE)

# Lichte stopwoordfilter voor retrieval (klinische inhoud telt, ruis niet)
_STOP = {
    "de", "het", "een", "en", "of", "met", "voor", "van", "op", "in", "te",
    "is", "was", "zijn", "wordt", "die", "dat", "bij", "naar", "aan", "om",
    "patient", "patiënt", "meneer", "mevrouw", "dhr", "mevr",
}


# ──────────────────────────────────────────────────────────────────────
# PII-scrubber (defense-in-depth)
# ──────────────────────────────────────────────────────────────────────

_RE_EMAIL = re.compile(r"\b[\w.\-]+@[\w.\-]+\.\w+\b")
_RE_LONGNUM = re.compile(r"\b\d{7,}\b")          # BSN, telefoon, dossiernummers
_RE_PHONE = re.compile(r"\b0\d[\d\s\-]{7,}\d\b")
_RE_AANHEF_NAAM = re.compile(
    r"\b(dhr\.?|mevr\.?|meneer|mevrouw|de heer)\s+[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)?",
    flags=re.IGNORECASE,
)


def scrub_pii(text: str) -> str:
    """Verwijder evidente persoonsgegevens. Conservatief: laat klinische tekst
    intact, vervang alleen duidelijke identifiers."""
    if not text:
        return ""
    text = _RE_EMAIL.sub("[email]", text)
    text = _RE_PHONE.sub("[telefoon]", text)
    text = _RE_LONGNUM.sub("[nummer]", text)
    text = _RE_AANHEF_NAAM.sub("[naam]", text)
    return text


# ──────────────────────────────────────────────────────────────────────
# Datamodel
# ──────────────────────────────────────────────────────────────────────

@dataclass
class FewShotExample:
    id: str
    index_text: str            # klinische samenvatting voor retrieval
    soep: Dict[str, str]       # {"S","O","E","P","icpc_code","icpc_titel"}

    def to_dict(self) -> dict:
        return {"id": self.id, "index_text": self.index_text, "soep": self.soep}

    @staticmethod
    def from_dict(d: dict) -> "FewShotExample":
        return FewShotExample(
            id=str(d.get("id", "")),
            index_text=d.get("index_text", ""),
            soep=d.get("soep", {}) or {},
        )


def _tokens(text: str) -> List[str]:
    return [t for t in _WORD_RE.findall((text or "").lower()) if t not in _STOP and len(t) > 2]


def build_index_text(soep: Dict[str, str]) -> str:
    """Maak de retrieval-index uit de klinisch meest onderscheidende velden:
    S (klacht) en E (evaluatie/diagnose)."""
    parts = [soep.get("S", ""), soep.get("E", ""), soep.get("icpc_titel", "")]
    return scrub_pii(" ".join(p for p in parts if p)).strip()


def build_query_from_extraction(extraction: Dict) -> str:
    """Vorm een retrieval-query uit de extractie van het huidige consult."""
    klachten = extraction.get("klachten", []) or []
    anamnese = extraction.get("anamnese", {}) or {}
    parts = list(klachten)
    parts.append(anamnese.get("hoofdklacht_details", ""))
    parts.extend(anamnese.get("bijkomende_klachten", []) or [])
    return " ".join(p for p in parts if p)


# ──────────────────────────────────────────────────────────────────────
# Bank
# ──────────────────────────────────────────────────────────────────────

@dataclass
class FewShotBank:
    examples: List[FewShotExample] = field(default_factory=list)
    _medical_terms: Optional[set] = None

    # ---- IO ----
    @staticmethod
    def load(path) -> "FewShotBank":
        p = Path(path)
        if not p.exists():
            return FewShotBank()
        data = json.loads(p.read_text(encoding="utf-8"))
        return FewShotBank([FewShotExample.from_dict(d) for d in data])

    def save(self, path) -> int:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps([e.to_dict() for e in self.examples], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return len(self.examples)

    # ---- Mutatie ----
    def upsert(self, example: FewShotExample) -> None:
        for i, e in enumerate(self.examples):
            if e.id == example.id:
                self.examples[i] = example
                return
        self.examples.append(example)

    # ---- Retrieval ----
    def _term_set(self) -> set:
        if self._medical_terms is None:
            try:
                from shared.evaluation import default_medical_terms
                self._medical_terms = {t.lower() for t in default_medical_terms()}
            except Exception:
                self._medical_terms = set()
        return self._medical_terms

    def _score(self, query_tokens: set, example: FewShotExample) -> float:
        ex_tokens = set(_tokens(example.index_text))
        if not query_tokens or not ex_tokens:
            return 0.0
        terms = self._term_set()
        shared = query_tokens & ex_tokens
        if not shared:
            return 0.0
        # Gewogen overlap: medische termen tellen dubbel (klinische relevantie)
        weight = sum(2.0 if t in terms else 1.0 for t in shared)
        union = sum(2.0 if t in terms else 1.0 for t in (query_tokens | ex_tokens))
        return weight / union if union else 0.0

    def select(self, query_text: str, k: int = 3, min_score: float = 0.05) -> List[FewShotExample]:
        """Geef de top-k meest gelijkende goedgekeurde SOEP's voor deze query."""
        query_tokens = set(_tokens(query_text))
        if not query_tokens or not self.examples:
            return []
        scored = [(self._score(query_tokens, e), e) for e in self.examples]
        scored = [(s, e) for s, e in scored if s >= min_score]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:k]]
