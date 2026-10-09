"""
Few-shot koude start (seed)
===========================

Laadt gecureerde, synthetische SOEP-voorbeelden in de few-shot-bank zodat de
SOEP-generatie vanaf dag 1 - vóór er echte artsfeedback is - een sterke
stijl-ankering heeft. De voorbeelden bevatten GEEN patiëntdata en sturen alleen
de stijl (de prompt zegt expliciet: neem de stijl over, nooit de inhoud).

Zodra echte goedgekeurde SOEP's binnenkomen, vult `tools/build_fewshot_bank.py`
de bank met praktijkeigen voorbeelden; seed- en praktijkvoorbeelden leven naast
elkaar (seed-id's beginnen met 'seed_').
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from services.learning.fewshot_bank import (
    FewShotBank,
    FewShotExample,
    build_index_text,
)

DEFAULT_SEED_PATH = str(
    Path(__file__).parent / "seed_data" / "soep_seed_examples.json"
)


def load_seed_examples(seed_path: str = DEFAULT_SEED_PATH) -> List[FewShotExample]:
    """Lees de seed-JSON en bouw FewShotExample-objecten (met retrieval-index)."""
    data = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    raw = data.get("examples", data) if isinstance(data, dict) else data
    examples = []
    for item in raw:
        soep = item.get("soep", {}) or {}
        if not (soep.get("S") and soep.get("E")):
            continue
        examples.append(FewShotExample(
            id=str(item.get("id", "")),
            index_text=build_index_text(soep),
            soep=soep,
        ))
    return examples


def seed_bank(
    bank_path: str,
    seed_path: str = DEFAULT_SEED_PATH,
) -> Tuple[int, int]:
    """Voeg de seed-voorbeelden toe aan de bank (idempotent via upsert op id).

    Returns (aantal_seed_voorbeelden, totaal_in_bank).
    """
    bank = FewShotBank.load(bank_path)
    seeds = load_seed_examples(seed_path)
    for ex in seeds:
        bank.upsert(ex)
    bank.save(bank_path)
    return len(seeds), len(bank.examples)
