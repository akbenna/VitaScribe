"""Post: labuitslagen en brieven beoordelen."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import main, post
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
LAB = (
    "Afzender\tDiagnostiek voor U\n"
    "Patiënt\tMFH Gorris - Aarts 26-10-1961 De Eerensstraat 4 6045 HB ROERMOND\n"
    "DATUM: 15-09-2026 09:48\nIdentificatienummer: 625805083\n"
    "Bepaling\tWaarde\tEenheid\tMin\tMax\n"
    "gamma-glutamyltransferase (gammaGT)\t*\t330\tU/L\t\t38\n"
    "alanineaminotransferase (ALAT;SGPT)\t*\t64\tU/L\t\t34\n"
    "creatinine\t58\tumol/L\t49\t90\n"
)
ANTWOORD = {
    "soort": "lab",
    "samenvatting": "Labuitslag DM-controle: gammaGT 330 en ALAT 64 verhoogd, nierfunctie goed; beoordelen via aanvrager.",
    "patient": "Uw bloeduitslag is binnen. Twee leverwaarden zijn wat verhoogd. De huisarts bekijkt dit samen met eerdere uitslagen.",
    "brief": {"afzender": "", "reden": "", "conclusie": "", "acties": []},
    "lab": {
        "bevindingen": [
            {"bepaling": "gammaGT", "waarde": "330 U/L", "richting": "hoog", "duiding": "fors verhoogd, cholestase of alcohol"},
            {"bepaling": "ALAT", "waarde": "64 U/L", "richting": "hoog", "duiding": "licht verhoogd"},
        ],
        "oordeel": "niet_beoordeelbaar",
        "beleid": "Beoordelen via aanvrager (kliniek, vorige waarden).",
        "vergelijking": "",
    },
    "let_op": "",
}


def fake_complete(antwoord, seen=None):
    async def _complete(system, user, provider=None, json_mode=False, max_tokens=None,
                        cache_system=False, quality=False, json_schema=None):
        if seen is not None:
            seen.append(dict(system=system, user=user, quality=quality, schema=json_schema))
        return antwoord if isinstance(antwoord, str) else json.dumps(antwoord)
    return _complete


def post_(api, body, antwoord=ANTWOORD, seen=None):
    with patch.object(post.llm_service, "complete", fake_complete(antwoord, seen)):
        return api.post("/api/v1/post/beoordeel", headers=H, json=body)


def test_lab_met_duiding_en_beleid(api):
    seen = []
    resp = post_(api, {"tekst": LAB, "leeftijd": 64, "problemen": ["T90.02 Diabetes mellitus type 2"], "cds": True}, seen=seen)
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["soort"] == "lab" and d["brief"] is None
    assert d["lab"]["oordeel"] == "niet_beoordeelbaar"
    assert "aanvrager" in d["lab"]["beleid"]
    assert d["patient"].startswith("Uw bloeduitslag")
    assert d["lab"]["bevindingen"][0]["duiding"]
    user = seen[0]["user"]
    # naam, geboortedatum, adres en identificatienummer gaan niet mee; leeftijd en episodes wel
    for geheim in ("Gorris", "26-10-1961", "Eerensstraat", "6045 HB", "625805083"):
        assert geheim not in user, geheim
    assert "LEEFTIJD: 64 jaar" in user and "T90.02 Diabetes" in user and "gammaGT" in user
    assert "Beoordelen via aanvrager" in seen[0]["system"] and seen[0]["quality"]


def test_zonder_cds_alleen_feiten(api):
    seen = []
    d = post_(api, {"tekst": LAB, "cds": False}, seen=seen).json()
    assert d["cds"] is False
    assert d["lab"]["oordeel"] == "onbekend" and d["lab"]["beleid"] == ""
    assert all(b["duiding"] == "" for b in d["lab"]["bevindingen"])
    assert "Klinische duiding staat op deze server uit" in seen[0]["system"]


def test_server_zonder_cds(api, monkeypatch):
    monkeypatch.setenv("CLINICAL_DECISION_SUPPORT", "false")
    d = post_(api, {"tekst": LAB, "cds": True}).json()
    assert d["cds"] is False and d["lab"]["oordeel"] == "onbekend"


def test_brief_samenvatten(api):
    brief = dict(ANTWOORD, soort="brief", samenvatting="Brief cardioloog: AF, apixaban gestart.",
                 brief={"afzender": "Cardiologie", "reden": "Palpitaties", "conclusie": "Paroxysmaal AF",
                        "acties": ["Nierfunctie over 3 mnd", "Herhaalrecept apixaban"]})
    d = post_(api, {"tekst": "Geachte collega, uw patiënt werd gezien wegens palpitaties ...", "cds": False}, antwoord=brief).json()
    assert d["soort"] == "brief" and d["lab"] is None
    assert d["brief"]["acties"] == ["Nierfunctie over 3 mnd", "Herhaalrecept apixaban"]


def test_fouten(api):
    assert post_(api, {"tekst": "kort"}).status_code == 422
    assert post_(api, {"tekst": LAB}, antwoord="geen json").status_code == 502
    assert api.post("/api/v1/post/beoordeel", json={"tekst": LAB}).status_code == 401


def test_audit_zonder_inhoud(api):
    with patch.object(post.llm_service, "complete", fake_complete(ANTWOORD)), \
         patch.object(post.audit, "log_event") as log:
        api.post("/api/v1/post/beoordeel", headers=H, json={"tekst": LAB, "cds": True})
    args, kwargs = log.call_args
    assert args[1] == "post.beoordeel"
    assert "gamma" not in json.dumps(kwargs).lower() and kwargs["kind"] == "lab"


def test_schema_is_strikt():
    def controleer(s):
        if s.get("type") == "object":
            assert s["additionalProperties"] is False
            assert set(s["required"]) == set(s["properties"])
            for v in s["properties"].values():
                controleer(v)
        if s.get("type") == "array":
            controleer(s["items"])
    controleer(post.SCHEMA)
