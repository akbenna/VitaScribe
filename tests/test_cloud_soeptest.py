"""SOEP-test: the same conversation to Claude and the EU model, with a fabrication check."""

import json

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import beheer, main, pipeline, register, soeptest
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_testset_is_complete_and_has_no_real_patients():
    consulten = soeptest.index()
    assert len(consulten) >= 4
    for c in consulten:
        tekst = soeptest.gesprek_uit_testset(c["id"])
        assert tekst.startswith("Spreker 1:") and len(tekst) > 2000
        assert c["bron"] and c["valkuilen"]
        assert "BSN" not in tekst and "geboren op" not in tekst


def test_fabrication_check():
    rug = soeptest.gesprek_uit_testset("01-lage-rugpijn")
    v = soeptest.verdacht([{"p": "Paracetamol max 6dd500mg (3x2)", "o": "drukpijn rechts"}], rug)
    assert v == ["hoeveelheid niet in het gesprek: 500mg"]
    assert soeptest.verdacht([{"p": "Paracetamol 3dd2, max 6 per dag", "o": "drukpijn rechts"}], rug) == []
    enkel = soeptest.gesprek_uit_testset("02-verzwikte-enkel")
    assert "plaats niet in het gesprek: lateraal" in soeptest.verdacht([{"o": "drukpijn li lateraal"}], enkel)
    borst = soeptest.gesprek_uit_testset("03-pijn-op-de-borst")
    v = soeptest.verdacht([{"e": "cardiale oorzaak uitgesloten", "o": "RR 120/80"}], borst)
    assert any("120/80" in x for x in v) and any("uitgesloten" in x for x in v)
    assert "zijde niet in het gesprek: rechts" in soeptest.verdacht([{"o": "pijn rechts"}], "Spreker 1: pijn links")


def test_soeptest_endpoint(monkeypatch):
    gezien = []

    async def fake_soep(gesprek, aanbieder=None, taal=None):
        gezien.append(aanbieder)
        if aanbieder == "mistral":
            return pipeline.SOEPResult(problemen=[{"s": "rugpijn", "o": "", "e": "Lage rugpijn",
                                                   "p": "Paracetamol 6dd500mg", "icpc_code": "L03", "icpc_titel": ""}])
        return pipeline.SOEPResult(problemen=[{"s": "rugpijn", "o": "", "e": "Lage rugpijn", "p": "Paracetamol 3dd2",
                                               "icpc_code": "L03", "icpc_titel": ""}])

    logs = []

    async def log(door, handeling, praktijk_id=None, **details):
        logs.append(details)

    monkeypatch.setattr(pipeline, "genereer_soep", fake_soep)
    monkeypatch.setattr(register, "log", log)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test"
    try:
        api = TestClient(main.app)
        lijst = api.get("/api/v1/beheer/testset").json()["consulten"]
        assert lijst and "gesprek" not in lijst[0]
        r = api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert sorted(gezien) == ["anthropic", "mistral"] and d["eu_model"] == "mistral"
        assert d["claude"]["verdacht"] == [] and d["eu"]["verdacht"] == ["hoeveelheid niet in het gesprek: 500mg"]
        assert d["valkuilen"]
        assert logs and "Paracetamol" not in json.dumps(logs)   # no report text in the log
        assert api.post("/api/v1/beheer/soeptest", json={"id": "bestaat-niet"}).status_code == 404
        assert api.post("/api/v1/beheer/soeptest", json={"gesprek": " "}).status_code == 400
        assert api.post("/api/v1/beheer/soeptest", json={"gesprek": "Spreker 1: keelpijn"}).status_code == 200
    finally:
        main.app.dependency_overrides.clear()


def test_soeptest_needs_admin():
    api = TestClient(main.app)
    assert api.get("/api/v1/beheer/testset").status_code in (401, 403, 503)
    assert api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn"}).status_code in (401, 403, 503)
