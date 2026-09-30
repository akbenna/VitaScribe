"""Meedenken bij de SOEP: medicatie altijd, beleid en Thuisarts alleen met CDS."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import main, meedenken
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("CLINICAL_DECISION_SUPPORT", "true")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


H = {"X-API-Key": "geheim"}
SOEP = {
    "s": "Sinds 2 dagen branderige mictie, geen koorts. Gebruikt metformine.",
    "o": "Nitriet positief.",
    "e": "Cystitis, ongecompliceerd.",
    "p": "Nitro furantoïne 100 mg 2dd 5 dagen. Ruim drinken.",
    "icpc_code": "U71", "icpc_titel": "Cystitis",
}
ANTWOORD = {
    "medicatie": [
        {"veld": "p", "genoemd": "Nitro furantoïne 100 mg", "middel": "nitrofurantoïne",
         "vervang": "nitrofurantoïne 100 mg", "zeker": True, "opmerking": "Let op nierfunctie."},
        {"veld": "p", "genoemd": "metformine", "middel": "metformine",   # staat in S, niet in P
         "vervang": "", "zeker": True, "opmerking": ""},
        {"veld": "p", "genoemd": "ciproxin", "middel": "ciprofloxacine",  # staat nergens: geen knop
         "vervang": "ciprofloxacine", "zeker": True, "opmerking": ""},
        {"veld": "p", "genoemd": "Ruim drinken", "middel": "?", "vervang": "iets", "zeker": False, "opmerking": ""},
    ],
    "beleid": {"oordeel": "in_lijn", "richtlijn": "NHG-Standaard Urineweginfecties",
               "toelichting": "zou weg moeten bij in_lijn",
               "suggesties": ["Vangnet bij koorts of flankpijn", "b", "c", "d"]},
    "thuisarts": ["blaasontsteking", "https://www.thuisarts.nl/x", "plassen", "derde"],
}


def fake_complete(antwoord, seen=None):
    async def _complete(system, user, provider=None, json_mode=False, max_tokens=None,
                        cache_system=False, quality=False, json_schema=None):
        if seen is not None:
            seen.append(dict(system=system, user=user, quality=quality, schema=json_schema, json_mode=json_mode))
        return antwoord if isinstance(antwoord, str) else json.dumps(antwoord)
    return _complete


def post(api, body, antwoord=ANTWOORD, seen=None):
    with patch.object(meedenken.llm_service, "complete", fake_complete(antwoord, seen)):
        return api.post("/api/v1/soep/meedenken", headers=H, json=body)


def test_medicatie_vervangen_alleen_als_het_letterlijk_in_de_soep_staat(api):
    resp = post(api, {"soep": SOEP, "cds": True})
    assert resp.status_code == 200, resp.text
    med = resp.json()["medicatie"]
    assert med[0]["vervang"] == "nitrofurantoïne 100 mg" and med[0]["veld"] == "p"
    assert med[1]["veld"] == "s"                 # gevonden in S, veld bijgesteld
    assert med[2]["vervang"] == ""               # "ciproxin" staat nergens: geen knop
    assert med[3]["vervang"] == ""               # niet zeker: geen knop


def test_beleid_en_thuisarts_met_cds_begrensd(api):
    seen = []
    data = post(api, {"soep": SOEP, "cds": True}, seen=seen).json()
    assert data["cds"] is True
    b = data["beleid"]
    assert b["oordeel"] == "in_lijn" and b["toelichting"] == ""
    assert len(b["suggesties"]) == 3
    assert data["thuisarts"] == ["blaasontsteking", "plassen"]   # geen URL's, hooguit 2
    assert data["medicatie"][0]["opmerking"] == "Let op nierfunctie."
    assert "TAAK 2" in seen[0]["system"] and seen[0]["quality"] and seen[0]["json_mode"]
    assert "E: Cystitis" in seen[0]["user"] and "ICPC: U71 Cystitis" in seen[0]["user"]


def test_zonder_keuze_van_de_arts_alleen_medicatie(api):
    seen = []
    data = post(api, {"soep": SOEP, "cds": False}, seen=seen).json()
    assert data["cds"] is False and data["beleid"] is None and data["thuisarts"] == []
    assert data["medicatie"][0]["opmerking"] == ""
    assert "TAAK 2" not in seen[0]["system"]


def test_server_staat_geen_cds_toe_dan_ook_niet(api, monkeypatch):
    monkeypatch.setenv("CLINICAL_DECISION_SUPPORT", "false")
    seen = []
    data = post(api, {"soep": SOEP, "cds": True}, seen=seen).json()
    assert data["cds"] is False and data["beleid"] is None
    assert "TAAK 2" not in seen[0]["system"]


def test_lege_soep_en_onleesbaar_antwoord(api):
    assert post(api, {"soep": {"s": "", "p": ""}}).status_code == 400
    resp = post(api, {"soep": SOEP}, antwoord="geen json")
    assert resp.status_code == 502


def test_zonder_sleutel_geweigerd(api):
    assert api.post("/api/v1/soep/meedenken", json={"soep": SOEP}).status_code == 401


def test_bsn_gaat_niet_mee_en_audit_zonder_inhoud(api):
    seen = []
    soep = dict(SOEP, s=SOEP["s"] + " BSN 123456789")
    with patch.object(meedenken.llm_service, "complete", fake_complete(ANTWOORD, seen)), \
         patch.object(meedenken.audit, "log_event") as log:
        api.post("/api/v1/soep/meedenken", headers=H, json={"soep": soep, "cds": True})
    assert "123456789" not in seen[0]["user"]
    args, kwargs = log.call_args
    assert args[1] == "soep.meedenken"
    assert "nitro" not in json.dumps(kwargs).lower() and "cystitis" not in json.dumps(kwargs).lower()


def test_schema_is_strikt():
    # Structured outputs require every property listed as required.
    def controleer(s):
        if s.get("type") == "object":
            assert s["additionalProperties"] is False
            assert set(s["required"]) == set(s["properties"])
            for v in s["properties"].values():
                controleer(v)
        if s.get("type") == "array":
            controleer(s["items"])
    controleer(meedenken.SCHEMA)


def test_vervang_voegt_niets_toe():
    # Echte uitkomst uit de praktijktest: het model zette er "mga" bij.
    assert meedenken.alleen_herstel("nitrofurantoïne mga 100 mg 2dd", "Nitro furan toïne 100 mg 2dd",
                                     "nitrofurantoïne") == "nitrofurantoïne 100 mg 2dd"
    assert meedenken.alleen_herstel("Amoxicilline 3dd 250 mg", "Amoxy cilline 3dd 250 mg",
                                     "amoxicilline") == "Amoxicilline 3dd 250 mg"
    assert meedenken.alleen_herstel("metoprolol retard 50 mg", "meta prolol 50 mg", "metoprolol") == "metoprolol 50 mg"
