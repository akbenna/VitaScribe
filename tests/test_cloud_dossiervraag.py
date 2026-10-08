"""Dossiervraag: een vraag aan het geopende dossier, met gecontroleerde bronnen."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import dossiervraag, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


# Since 07-10-2026 the default mode is eu; these tests run the claude mode (Anthropic).
H = {"X-API-Key": "geheim", "X-VitaScribe-Modus": "claude"}
DOSSIER = (
    "PATIËNT: J.J.\n"
    "== JOURNAAL ==\n"
    "14-02-2025 U71 Cystitis. Urinekweek: E. coli, resistent voor  amoxicilline en trimethoprim; "
    "gevoelig voor nitrofurantoïne. Start nitrofurantoïne 100 mg 2dd 5 dagen.\n"
    "03-09-2024 U71 Cystitis, nitriet pos. Fosfomycine 3 g eenmalig.\n"
    "== LAB ==\n"
    "10-01-2025 eGFR 72, kreatinine 88.\n"
)


def fake_complete(antwoord, seen=None):
    async def _complete(system, user, provider=None, json_mode=False, max_tokens=None,
                        cache_system=False, quality=False, json_schema=None):
        if seen is not None:
            seen.append(dict(system=system, user=user, provider=provider, json_mode=json_mode,
                             cache_system=cache_system, quality=quality, schema=json_schema))
        return antwoord if isinstance(antwoord, str) else json.dumps(antwoord)
    return _complete


def test_citaat_wordt_letterlijk_gecontroleerd():
    norm = dossiervraag._norm(DOSSIER)
    # extra spaties en hoofdletters maken niet uit
    assert dossiervraag.citaat_klopt("resistent voor amoxicilline en Trimethoprim", norm)
    # weggelaten stuk met beletselteken: beide delen moeten er staan
    assert dossiervraag.citaat_klopt("Urinekweek: E. coli … gevoelig voor nitrofurantoïne", norm)
    # verzonnen of geparafraseerd: niet geverifieerd
    assert not dossiervraag.citaat_klopt("resistent voor ciprofloxacine", norm)
    assert not dossiervraag.citaat_klopt("", norm)
    assert not dossiervraag.citaat_klopt("...", norm)


def test_vraag_geeft_antwoord_met_gecontroleerde_bronnen(api):
    seen = []
    antwoord = {
        "antwoord": "Laatste kweek 14-02-2025: E. coli, resistent voor amoxicilline en trimethoprim.",
        "gevonden": True,
        "bronnen": [
            {"datum": "14-02-2025", "onderdeel": "JOURNAAL",
             "citaat": "E. coli, resistent voor  amoxicilline en trimethoprim"},
            {"datum": "01-01-2023", "onderdeel": "LAB", "citaat": "ESBL positief"},
        ],
        "let_op": "",
    }
    with patch.object(dossiervraag.llm_service, "complete", fake_complete(antwoord, seen)):
        resp = api.post("/api/v1/dossier/vraag", headers=H, json={
            "dossier": DOSSIER + "BSN 123456789", "vraag": "Laatste kweken en resistentie?",
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["gevonden"] is True
    assert [b["geverifieerd"] for b in data["bronnen"]] == [True, False]
    call = seen[0]
    # het dossier staat in de gecachte system-prompt; het BSN is eruit
    assert "resistent voor" in call["system"] and "123456789" not in call["system"]
    assert call["cache_system"] and call["quality"] and call["json_mode"]
    assert call["schema"] is dossiervraag.ANTWOORD_SCHEMA
    assert call["provider"] == "anthropic"
    assert "Laatste kweken en resistentie?" in call["user"]


def test_vervolgvraag_krijgt_eerdere_vragen_mee(api):
    seen = []
    antwoord = {"antwoord": "Ja.", "gevonden": True, "bronnen": [], "let_op": ""}
    eerder = [{"vraag": f"v{i}", "antwoord": f"a{i}"} for i in range(5)]
    with patch.object(dossiervraag.llm_service, "complete", fake_complete(antwoord, seen)):
        resp = api.post("/api/v1/dossier/vraag", headers=H,
                        json={"dossier": DOSSIER, "vraag": "En daarvoor?", "eerder": eerder})
    assert resp.status_code == 200
    user = seen[0]["user"]
    # alleen de laatste drie, in volgorde, en de nieuwe vraag als laatste
    assert "v1" not in user and user.index("v2") < user.index("v4") < user.index("En daarvoor?")


def test_niet_gevonden_en_json_in_codeblok(api):
    raw = '```json\n{"antwoord": "Geen echo buik gevonden.", "gevonden": false, "bronnen": [], "let_op": "Correspondentie niet ingelezen."}\n```'
    with patch.object(dossiervraag.llm_service, "complete", fake_complete(raw)):
        resp = api.post("/api/v1/dossier/vraag", headers=H,
                        json={"dossier": DOSSIER, "vraag": "Ooit een echo buik?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["gevonden"] is False and data["let_op"].startswith("Correspondentie")


def test_onleesbaar_antwoord_geeft_nette_fout(api):
    with patch.object(dossiervraag.llm_service, "complete", fake_complete("geen json")):
        resp = api.post("/api/v1/dossier/vraag", headers=H, json={"dossier": DOSSIER, "vraag": "Allergieën?"})
    assert resp.status_code == 502
    assert "opnieuw" in resp.json()["detail"]


def test_zonder_sleutel_geweigerd_en_leeg_dossier_ongeldig(api):
    assert api.post("/api/v1/dossier/vraag", json={"dossier": DOSSIER, "vraag": "x?"}).status_code == 401
    assert api.post("/api/v1/dossier/vraag", headers=H, json={"dossier": "kort", "vraag": "x?"}).status_code == 422


def test_audit_bevat_geen_inhoud(api):
    antwoord = {"antwoord": "Nitrofurantoïne 02-2025.", "gevonden": True, "bronnen": [], "let_op": ""}
    with patch.object(dossiervraag.llm_service, "complete", fake_complete(antwoord)), \
         patch.object(dossiervraag.audit, "log_event") as log:
        api.post("/api/v1/dossier/vraag", headers=H, json={"dossier": DOSSIER, "vraag": "Antibiotica?"})
    args, kwargs = log.call_args
    assert args[1] == "dossier.vraag"
    assert "Antibiotica" not in json.dumps(kwargs) and "nitro" not in json.dumps(kwargs).lower()


def test_indirecte_aanwijzingen_en_oude_antwoordvorm(api):
    seen = []
    antwoord = {"antwoord": "Niet expliciet vermeld. Aanwijzingen: episode urine-incontinentie (2013).",
                "zekerheid": "indirect",
                "bronnen": [{"datum": "", "onderdeel": "EPISODES", "citaat": "Nitrofurantoïne 5 dagen"}],
                "let_op": "Mogelijk in een brief van de uroloog."}
    with patch.object(dossiervraag.llm_service, "complete", fake_complete(antwoord, seen)):
        d = api.post("/api/v1/dossier/vraag", headers=H, json={"dossier": DOSSIER, "vraag": "Indicatie katheter?"}).json()
    assert d["zekerheid"] == "indirect" and d["gevonden"] is True
    # de prompt zoekt breed, met synoniemen, en meldt een mogelijke andere patiënt
    assert "synoniemen" in seen[0]["system"] and "andere patiënt" in seen[0]["system"]
    assert seen[0]["schema"]["properties"]["zekerheid"]["enum"] == ["expliciet", "indirect", "niet_gevonden"]
    oud = {"antwoord": "x", "gevonden": False, "bronnen": [], "let_op": ""}
    with patch.object(dossiervraag.llm_service, "complete", fake_complete(oud)):
        d = api.post("/api/v1/dossier/vraag", headers=H, json={"dossier": DOSSIER, "vraag": "MRI?"}).json()
    assert d["zekerheid"] == "niet_gevonden" and d["gevonden"] is False
