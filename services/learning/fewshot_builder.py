"""
Few-shot-bank builder
======================

Vult de few-shot-bank uit door de arts goedgekeurde SOEP's
(consultation_feedback.soep_corrected). Lokaal en gepseudonimiseerd.

Pure aggregatie blijft in fewshot_bank.py; hier zit de DB/IO (raw SQL), met
dezelfde optionele-SQLAlchemy-aanpak als de vocabulaire-learner zodat de job
ook met een injecteerbare sessie testbaar is.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

import structlog

from services.learning.fewshot_bank import (
    FewShotBank,
    FewShotExample,
    build_index_text,
    scrub_pii,
)

logger = structlog.get_logger()

try:
    from sqlalchemy import text as _sa_text
except Exception:  # pragma: no cover
    _sa_text = None


def _sql(query: str):
    return _sa_text(query) if _sa_text is not None else query


def _as_dict(value) -> Dict:
    """JSONB komt soms als dict, soms als string terug - normaliseer."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


@dataclass
class FewShotBuildReport:
    feedback_rows: int = 0
    examples: int = 0
    skipped: int = 0

    def to_dict(self) -> dict:
        return {
            "feedback_rows": self.feedback_rows,
            "examples": self.examples,
            "skipped": self.skipped,
        }


class FewShotBankBuilder:
    def __init__(self, path: Optional[str] = None, max_examples: Optional[int] = None):
        self.path = path or os.getenv(
            "FEWSHOT_BANK_PATH", "/data/fewshot/soep_examples.json"
        )
        self.max_examples = max_examples or int(os.getenv("FEWSHOT_MAX_EXAMPLES", "500"))

    async def fetch_rows(self, session):
        rows = await session.execute(_sql(
            """
            SELECT id, soep_corrected
            FROM consultation_feedback
            WHERE soep_corrected IS NOT NULL
            ORDER BY created_at DESC
            """
        ))
        return rows.all()

    async def run(self, session) -> FewShotBuildReport:
        report = FewShotBuildReport()
        bank = FewShotBank.load(self.path)

        rows = await self.fetch_rows(session)
        report.feedback_rows = len(rows)

        for row in rows:
            fid, soep_raw = row[0], row[1]
            soep = _as_dict(soep_raw)
            # Minimale kwaliteitseis: er moet S én E zijn (klacht + evaluatie)
            if not (soep.get("S") and soep.get("E")):
                report.skipped += 1
                continue
            clean_soep = {k: scrub_pii(str(v)) if isinstance(v, str) else v
                          for k, v in soep.items()}
            example = FewShotExample(
                id=str(fid),
                index_text=build_index_text(clean_soep),
                soep=clean_soep,
            )
            bank.upsert(example)
            report.examples += 1

        # Begrens de bank (meest recente eerst behouden)
        if len(bank.examples) > self.max_examples:
            bank.examples = bank.examples[-self.max_examples:]

        bank.save(self.path)
        logger.info(
            "fewshot.build_complete",
            path=self.path,
            feedback_rows=report.feedback_rows,
            examples=report.examples,
            skipped=report.skipped,
            bank_size=len(bank.examples),
        )
        return report
