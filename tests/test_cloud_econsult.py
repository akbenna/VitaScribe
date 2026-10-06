"""E-consult: concept-antwoord uit het dossier; NHG alleen aangevinkt én toegestaan."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import econsult, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.delenv("CLINICAL_DECISION_SUPPORT", raising=False)
    monkeypatch.delenv("ECONSULT_NHG_IN_EU", raising=False)
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


H = {"X-API-Key": "geheim"}
EU = {"X-API-Key": "geheim", "X-VitaScribe-Modus": "eu"}
BERICHT = "Dokter, mag ik ibuprofen nemen voor mijn knie? Ik gebruik al bloedverdunners."
DOSSIER = (
    "PATIËNT: J.J.\n"
    "== DOSSIER (IN BEELD) ==\n"
    "E-consult 05-10-2026\n" + BERICHT + "\n"
    "== MEDICATIE ==\n"
    "apixaban 5 mg 2dd sinds 12-03-2024\n"
    "== JOURNAAL ==\n"
    "12-03-2024 K78 Atriumfibrilleren, start apixaban.\n"
)

ANTWOORD = {
    "bericht": BERICHT,
    "vraag_kort": "Mag ibuprofen naast een bloedverdunner?",
    "feiten": [
        {"tekst": "Gebruikt apixaban.", "datum": "12-03-2024", "onderdeel": "MEDICATIE",
         "citaat": "apixaban 5 mg 2dd"},
        {"tekst": "Maagbloeding.", "datum": "2020", "onderdeel": "JOURNAAL", "citaat": "ulcus duodeni 2020"},
    ],
    "nhg": {"richtlijn": "NHG-Standaard Pijn", "punten": ["Liever paracetamol."],
            "alarm": ["zwarte ontlasting"], "schriftelijk_geschikt": True},
    "antwoord": "Beste [naam patiënt],\n\n[beleid aanvullen]\n\nMet vriendelijke groet,\n[Naam huisarts]",
    "journaal": "S: vraag ibuprofen naast apixaban. E: [beleid aanvullen] P: [beleid aanvullen]",
    "let_op": "",
}


def fake_complete(antwoord, seen=None):
    async def _complete(system, user, provider=None, json_mode=False, max_tokens=None,
                        cache_system=False, quality=False, json_schema=None):
        if seen is not None:
            seen.append(dict(system=system, user=user, provider=provider, schema=json_schema))
        return antwoord if isinstance(antwoord, str) else json.dumps(antwoord)
    return _complete


def test_concept_zonder_nhg_geeft_geen_advies(api):
    seen = []
    with patch.object(econsult.llm_service, "complete", fake_complete(ANTWOORD, seen)):
        r = api.post("/api/v1/econsult/concept", headers=H, json={"dossier": DOSSIER + "BSN 123456789"})
    assert r.status_code == 200, r.text
    d = r.json()
    # NHG not ticked: whatever the model returns, it is not shown
    assert d["nhg"] is None and d["nhg_gebruikt"] is False
    assert [f["geverifieerd"] for f in d["feiten"]] == [True, False]
    # message found in the dossier, and really there
    assert d["bericht"] == BERICHT and d["bericht_geverifieerd"] is True
    assert "[beleid aanvullen]" in d["antwoord"]
    system = seen[0]["system"]
    assert "GEEN medisch advies" in system and "NHG-MEEDENKEN" not in system
    assert "123456789" not in system
    assert "nog niet gegeven" in seen[0]["user"]


def test_nhg_aangevinkt_maar_niet_toegestaan(api):
    seen = []
    with patch.object(econsult.llm_service, "complete", fake_complete(ANTWOORD, seen)):
        r = api.post("/api/v1/econsult/concept", headers=H, json={"dossier": DOSSIER, "nhg": True})
    d = r.json()
    assert d["nhg"] is None and d["nhg_beschikbaar"] is False
    assert "NHG-MEEDENKEN" not in seen[0]["system"]


def test_nhg_aangevinkt_en_toegestaan(api, monkeypatch):
    monkeypatch.setenv("CLINICAL_DECISION_SUPPORT", "true")
    seen = []
    with patch.object(econsult.llm_service, "complete", fake_complete(ANTWOORD, seen)):
        r = api.post("/api/v1/econsult/concept", headers=H, json={
            "dossier": DOSSIER, "nhg": True, "beleid": "Paracetamol, geen ibuprofen.",
        })
    d = r.json()
    assert d["nhg_gebruikt"] is True
    assert d["nhg"]["richtlijn"] == "NHG-Standaard Pijn" and d["nhg"]["alarm"] == ["zwarte ontlasting"]
    assert "NHG-MEEDENKEN" in seen[0]["system"]
    assert "Paracetamol, geen ibuprofen." in seen[0]["user"]


def test_eu_modus_nhg_alleen_met_praktijkkeuze(api, monkeypatch):
    # CLINICAL_DECISION_SUPPORT does not unlock it in the eu mode ...
    monkeypatch.setenv("CLINICAL_DECISION_SUPPORT", "true")
    assert api.get("/api/v1/econsult/status", headers=EU).json() == {"nhg_beschikbaar": False}
    with patch.object(econsult.llm_service, "complete", fake_complete(ANTWOORD)):
        d = api.post("/api/v1/econsult/concept", headers=EU, json={"dossier": DOSSIER, "nhg": True}).json()
    assert d["nhg"] is None
    # ... the explicit practice choice does
    monkeypatch.setenv("ECONSULT_NHG_IN_EU", "true")
    assert api.get("/api/v1/econsult/status", headers=EU).json() == {"nhg_beschikbaar": True}
    seen = []
    with patch.object(econsult.llm_service, "complete", fake_complete(ANTWOORD, seen)):
        d = api.post("/api/v1/econsult/concept", headers=EU, json={"dossier": DOSSIER, "nhg": True}).json()
    assert d["nhg_gebruikt"] is True
    assert seen[0]["provider"] == "mistral"


def test_verzonnen_bericht_is_niet_geverifieerd(api):
    nep = dict(ANTWOORD, bericht="Ik wil graag een verwijzing naar de dermatoloog.")
    with patch.object(econsult.llm_service, "complete", fake_complete(nep)):
        d = api.post("/api/v1/econsult/concept", headers=H, json={"dossier": DOSSIER}).json()
    assert d["bericht_geverifieerd"] is False


def test_geplakt_bericht_gaat_voor(api):
    seen = []
    with patch.object(econsult.llm_service, "complete", fake_complete(dict(ANTWOORD, bericht="iets anders"), seen)):
        d = api.post("/api/v1/econsult/concept", headers=H, json={
            "dossier": DOSSIER, "bericht": "Kan ik mijn herhaalrecept ophalen?",
        }).json()
    assert d["bericht"] == "Kan ik mijn herhaalrecept ophalen?" and d["bericht_geverifieerd"] is True
    assert "BERICHT VAN DE PATIËNT:\nKan ik mijn herhaalrecept ophalen?" in seen[0]["user"]


def test_fout_van_het_model_geeft_502(api):
    with patch.object(econsult.llm_service, "complete", fake_complete("geen json")):
        r = api.post("/api/v1/econsult/concept", headers=H, json={"dossier": DOSSIER})
    assert r.status_code == 502


def test_sleutel_verplicht(api):
    assert api.post("/api/v1/econsult/concept", json={"dossier": DOSSIER}).status_code in (401, 403)
