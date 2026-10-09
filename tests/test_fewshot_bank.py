"""
Tests voor de few-shot-bank (services/learning/fewshot_bank.py),
de builder en de SOEP-promptintegratie.
"""

import asyncio
import json

from services.learning.fewshot_bank import (
    FewShotBank,
    FewShotExample,
    build_index_text,
    build_query_from_extraction,
    scrub_pii,
)
from services.learning.fewshot_builder import FewShotBankBuilder
from shared.prompts.templates import format_soep_examples


# ── PII-scrubber ──────────────────────────────────────────────────────

def test_scrub_pii_removes_identifiers():
    txt = "meneer Jansen, BSN 123456789, mail jan@example.com, tel 0612345678"
    out = scrub_pii(txt)
    assert "Jansen" not in out
    assert "123456789" not in out
    assert "jan@example.com" not in out
    assert "[naam]" in out and "[nummer]" in out and "[email]" in out


def test_scrub_pii_keeps_clinical_text():
    txt = "hypertensie, start metformine 500mg"
    assert "hypertensie" in scrub_pii(txt)
    assert "metformine" in scrub_pii(txt)


# ── Retrieval ─────────────────────────────────────────────────────────

def _bank():
    return FewShotBank([
        FewShotExample("1", build_index_text(
            {"S": "hoofdpijn sinds enkele dagen", "E": "spanningshoofdpijn"}),
            {"S": "hoofdpijn", "O": "geen LO", "E": "spanningshoofdpijn", "P": "paracetamol"}),
        FewShotExample("2", build_index_text(
            {"S": "hoesten en koorts", "E": "pneumonie"}),
            {"S": "hoesten", "O": "crepitaties", "E": "pneumonie", "P": "amoxicilline"}),
        FewShotExample("3", build_index_text(
            {"S": "pijn op de borst", "E": "angina pectoris"}),
            {"S": "pijn borst", "O": "RR 150/90", "E": "angina pectoris", "P": "verwijzing"}),
    ])


def test_select_returns_most_similar():
    bank = _bank()
    res = bank.select("patient met hoofdpijn en nekklachten", k=1)
    assert len(res) == 1
    assert res[0].id == "1"


def test_select_respects_k_and_minscore():
    bank = _bank()
    res = bank.select("hoesten koorts benauwd", k=2)
    assert res and res[0].id == "2"
    # Geen overlap -> niets
    assert bank.select("administratieve afspraak parkeren", k=3) == []


def test_select_empty_bank_is_safe():
    assert FewShotBank().select("hoofdpijn", k=3) == []


def test_build_query_from_extraction():
    q = build_query_from_extraction({
        "klachten": ["hoofdpijn"],
        "anamnese": {"hoofdklacht_details": "bonzend", "bijkomende_klachten": ["misselijk"]},
    })
    assert "hoofdpijn" in q and "misselijk" in q


# ── Promptformat ──────────────────────────────────────────────────────

def test_format_soep_examples_block():
    ex = FewShotExample("1", "idx", {"S": "s", "O": "o", "E": "e", "P": "p"})
    block = format_soep_examples([ex])
    assert "VOORBEELD 1" in block and "S: s" in block
    assert format_soep_examples([]) == ""


# ── IO roundtrip ──────────────────────────────────────────────────────

def test_bank_save_load_roundtrip(tmp_path):
    out = tmp_path / "bank.json"
    bank = _bank()
    bank.save(out)
    loaded = FewShotBank.load(out)
    assert len(loaded.examples) == 3
    assert loaded.examples[0].soep["E"] == "spanningshoofdpijn"


# ── Builder met FakeSession ───────────────────────────────────────────

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt, params=None):
        return _FakeResult(self._rows)


def test_builder_populates_bank_and_scrubs(tmp_path):
    out = tmp_path / "bank.json"
    # soep_corrected als dict (JSONB) en als string - beide moeten werken
    rows = [
        ("fb1", {"S": "meneer Jansen met hoofdpijn", "O": "geen LO",
                 "E": "spanningshoofdpijn", "P": "paracetamol"}),
        ("fb2", json.dumps({"S": "hoesten", "O": "", "E": "pneumonie", "P": "amoxicilline"})),
        ("fb3", {"S": "", "E": ""}),  # onvolledig -> overslaan
    ]
    builder = FewShotBankBuilder(path=str(out))
    report = asyncio.run(builder.run(_FakeSession(rows)))

    assert report.feedback_rows == 3
    assert report.examples == 2
    assert report.skipped == 1

    bank = FewShotBank.load(out)
    assert len(bank.examples) == 2
    # PII gescrubd in opgeslagen voorbeeld
    assert "Jansen" not in bank.examples[0].soep["S"]
