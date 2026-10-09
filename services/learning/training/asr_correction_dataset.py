"""
ASR-postcorrectie dataset (SFT)
===============================

Bouwt een supervised-fine-tuning dataset uit de transcriptcorrecties van de
arts: (ruw transcript -> gecorrigeerd transcript). GEEN audio nodig - werkt dus
ook binnen het privacybeleid dat audio na goedkeuring verwijdert.

Het getrainde model is een *contextuele* ASR-corrector, complementair aan de
deterministische woordenlijst (niveau 1): het vangt fouten die van de zinscontext
afhangen ("hoge tensie" -> "hypertensie") en die een statische lijst mist.

Pure builder (`build_asr_pairs`) + DB-export (`ASRDatasetBuilder`).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Tuple

import structlog

logger = structlog.get_logger()

try:
    from sqlalchemy import text as _sa_text
except Exception:  # pragma: no cover
    _sa_text = None


def _sql(query: str):
    return _sa_text(query) if _sa_text is not None else query


# Kwaliteitsgrenzen voor een bruikbaar SFT-paar
MIN_CHARS = 10
MAX_CHARS = 4000
MIN_SIMILARITY = 0.6   # paar moet grotendeels gelijk zijn (correctie, geen herschrijving)


def _quality_ok(original: str, corrected: str) -> bool:
    o = (original or "").strip()
    c = (corrected or "").strip()
    if not o or not c or o == c:
        return False
    if not (MIN_CHARS <= len(c) <= MAX_CHARS):
        return False
    # Volledige herschrijvingen (lage gelijkenis) zijn geen ASR-correctie
    if SequenceMatcher(None, o, c).ratio() < MIN_SIMILARITY:
        return False
    return True


def build_asr_pairs(feedback_pairs: List[Tuple[str, str]]) -> List[dict]:
    """Maak SFT-records {"input","target"} uit (origineel, gecorrigeerd)-paren."""
    records = []
    seen = set()
    for original, corrected in feedback_pairs:
        if not _quality_ok(original, corrected):
            continue
        key = (original.strip(), corrected.strip())
        if key in seen:
            continue
        seen.add(key)
        records.append({"input": original.strip(), "target": corrected.strip()})
    return records


@dataclass
class DatasetReport:
    feedback_rows: int = 0
    records: int = 0
    out_path: str = ""
    sufficient: bool = False

    def to_dict(self) -> dict:
        return {
            "feedback_rows": self.feedback_rows,
            "records": self.records,
            "out_path": self.out_path,
            "sufficient": self.sufficient,
        }


class ASRDatasetBuilder:
    def __init__(self, out_path: Optional[str] = None, min_pairs: Optional[int] = None):
        self.out_path = out_path or os.getenv(
            "ASR_DATASET_PATH", "/data/training/asr_correction.jsonl"
        )
        self.min_pairs = min_pairs if min_pairs is not None else int(
            os.getenv("ASR_MIN_PAIRS", "200")
        )

    async def fetch_pairs(self, session) -> List[Tuple[str, str]]:
        rows = await session.execute(_sql(
            """
            SELECT transcript_original, transcript_corrected
            FROM consultation_feedback
            WHERE transcript_original IS NOT NULL
              AND transcript_corrected IS NOT NULL
              AND transcript_original <> transcript_corrected
            """
        ))
        return [(r[0], r[1]) for r in rows.all()]

    def write_jsonl(self, records: List[dict]) -> None:
        p = Path(self.out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    async def run(self, session) -> DatasetReport:
        report = DatasetReport(out_path=self.out_path)
        pairs = await self.fetch_pairs(session)
        report.feedback_rows = len(pairs)
        records = build_asr_pairs(pairs)
        report.records = len(records)
        report.sufficient = report.records >= self.min_pairs
        self.write_jsonl(records)
        logger.info(
            "asr_dataset.exported",
            path=self.out_path,
            records=report.records,
            sufficient=report.sufficient,
            min_pairs=self.min_pairs,
        )
        if not report.sufficient:
            logger.warning(
                "asr_dataset.insufficient",
                records=report.records,
                needed=self.min_pairs,
            )
        return report
