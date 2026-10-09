"""
SOEP-voorkeursdataset (DPO)
===========================

Bouwt voorkeursparen voor Direct Preference Optimization uit de SOEP-feedback:
de door de arts goedgekeurde SOEP is 'chosen', de oorspronkelijk gegenereerde
SOEP is 'rejected'. Daarmee leert het model de praktijkstijl te prefereren -
exact het materiaal dat consultation_feedback opslaat.

Pure builder (`build_dpo_pairs`) + DB-export (`SoepDPODatasetBuilder`).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

try:
    from sqlalchemy import text as _sa_text
except Exception:  # pragma: no cover
    _sa_text = None


def _sql(query: str):
    return _sa_text(query) if _sa_text is not None else query


def _as_dict(value) -> Dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


_SOEP_FIELDS = ("S", "O", "E", "P", "icpc_code", "icpc_titel")

# Promptsjabloon voor DPO. De policy ziet het consult als context en moet een
# SOEP produceren; de voorkeur stuurt richting de artsstijl.
DPO_PROMPT_TEMPLATE = (
    "Schrijf een beknopte SOEP-notitie (telegramstijl) op basis van het volgende "
    "consult. Rapporteer alleen wat in het transcript staat.\n\nTRANSCRIPT:\n{transcript}"
)


def _serialize_soep(soep: Dict) -> str:
    """Compacte, stabiele JSON-weergave van de SOEP (zoals het model produceert)."""
    return json.dumps(
        {k: soep.get(k, "") for k in _SOEP_FIELDS},
        ensure_ascii=False,
    )


def _meaningfully_different(a: Dict, b: Dict) -> bool:
    for f in ("S", "O", "E", "P"):
        if (a.get(f, "") or "").strip() != (b.get(f, "") or "").strip():
            return True
    return False


def build_dpo_pairs(
    rows: List[Tuple[str, Dict, Dict]],
) -> List[dict]:
    """Maak DPO-records {"prompt","chosen","rejected"}.

    Args:
        rows: lijst van (transcript, soep_original, soep_corrected).
    """
    records = []
    for transcript, soep_original, soep_corrected in rows:
        orig = _as_dict(soep_original)
        corr = _as_dict(soep_corrected)
        # Eisen: er is een correctie (anders geen voorkeurssignaal) en de
        # goedgekeurde SOEP heeft minimaal S én E.
        if not (corr.get("S") and corr.get("E")):
            continue
        if not _meaningfully_different(orig, corr):
            continue
        prompt = DPO_PROMPT_TEMPLATE.format(transcript=(transcript or "").strip())
        records.append({
            "prompt": prompt,
            "chosen": _serialize_soep(corr),
            "rejected": _serialize_soep(orig),
        })
    return records


@dataclass
class DPOReport:
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


class SoepDPODatasetBuilder:
    def __init__(self, out_path: Optional[str] = None, min_pairs: Optional[int] = None):
        self.out_path = out_path or os.getenv(
            "DPO_DATASET_PATH", "/data/training/soep_dpo.jsonl"
        )
        self.min_pairs = min_pairs if min_pairs is not None else int(
            os.getenv("DPO_MIN_PAIRS", "200")
        )

    async def fetch_rows(self, session) -> List[Tuple[str, Dict, Dict]]:
        rows = await session.execute(_sql(
            """
            SELECT transcript_corrected, soep_original, soep_corrected
            FROM consultation_feedback
            WHERE soep_original IS NOT NULL
              AND soep_corrected IS NOT NULL
            """
        ))
        return [(r[0], r[1], r[2]) for r in rows.all()]

    def write_jsonl(self, records: List[dict]) -> None:
        p = Path(self.out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    async def run(self, session) -> DPOReport:
        report = DPOReport(out_path=self.out_path)
        rows = await self.fetch_rows(session)
        report.feedback_rows = len(rows)
        records = build_dpo_pairs(rows)
        report.records = len(records)
        report.sufficient = report.records >= self.min_pairs
        self.write_jsonl(records)
        logger.info(
            "dpo_dataset.exported",
            path=self.out_path,
            records=report.records,
            sufficient=report.sufficient,
            min_pairs=self.min_pairs,
        )
        if not report.sufficient:
            logger.warning(
                "dpo_dataset.insufficient",
                records=report.records,
                needed=self.min_pairs,
            )
        return report
