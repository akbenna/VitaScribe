"""Leren per arts: regels uit aanpassingen, zonder patiëntgegevens, per arts gescheiden."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import leren, llm_service, main, pipeline, tolk
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_USERS", "dr_a:sleutel-a,dr_b:sleutel-b")
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_config.cache_clear()
    leren._geheugen.__init__()
    leren._cache.clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


A = {"X-API-Key": "sleutel-a"}
B = {"X-API-Key": "sleutel-b"}


def nep_llm(antwoord, gezien=None):
    async def complete(system=None, user=None, provider=None, json_mode=False, max_tokens=None, cache_system=False,
                       quality=False, json_schema=None, model=None, system_prompt=None, user_prompt=None):
        if gezien is not None:
            gezien.append(dict(system=system or system_prompt, user=user or user_prompt, provider=provider))
        return antwoord if isinstance(antwoord, str) else json.dumps(antwoord)
    return complete


CONCEPT = {"s": "Patiënt geeft aan dat hij sinds 3 dagen hoest.", "o": "Pulm: VAG bdz.", "e": "Acute hoest", "p": "Afwachten."}
DEFINITIEF = {"s": "Sinds 3 dagen hoesten.", "o": "Pulm: VAG bdz.", "e": "Acute hoest", "p": "Afwachten, terug bij koorts."}


def test_aanpassing_wordt_regel_en_woord_als_voorstel(api, monkeypatch):
    gezien = []
    monkeypatch.setattr(llm_service, "complete", nep_llm({
        "regels": ["Schrijf in S geen 'patiënt geeft aan dat'; begin direct met de klacht.",
                   "Patiënt J. de Vries geboren 12-03-1961 heeft hoest."],   # patiëntgegevens: weg
        "woorden": [{"van": "meta prolol", "naar": "metoprolol"}]}, gezien))
    r = api.post("/api/v1/leren/soep", headers=A, json={"concept": CONCEPT, "definitief": DEFINITIEF, "markeringen": 1})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["gewijzigd_pct"] > 2
    soorten = sorted((v["soort"], v["status"]) for v in d["voorstellen"])
    assert soorten == [("soep", "voorstel"), ("woord", "voorstel")]
    assert not any("1961" in v["regel"] for v in d["voorstellen"])
    assert "Geen enkel gegeven van deze patiënt" in gezien[0]["system"]
    assert "DEFINITIEF DOOR DE ARTS" in gezien[0]["user"]


def test_geen_aanpassing_alleen_meten(api, monkeypatch):
    gezien = []
    monkeypatch.setattr(llm_service, "complete", nep_llm({"regels": []}, gezien))
    d = api.post("/api/v1/leren/soep", headers=A, json={"concept": CONCEPT, "definitief": CONCEPT}).json()
    assert d == {"gewijzigd_pct": 0.0, "voorstellen": []} and gezien == []
    m = api.get("/api/v1/leren/overzicht", headers=A).json()["meting"]
    assert m[0]["soort"] == "soep" and m[0]["aantal"] == 1


def test_goedkeuren_per_arts_en_mee_in_de_soep(api, monkeypatch):
    monkeypatch.setattr(llm_service, "complete", nep_llm({"regels": ["Gebruik li en re voor links en rechts."], "woorden": []}))
    v = api.post("/api/v1/leren/soep", headers=A, json={"concept": CONCEPT, "definitief": DEFINITIEF}).json()["voorstellen"][0]
    # Een voorstel gaat nog niet mee.
    leren.zet_eigenaar("naam:dr_a")
    assert asyncio.run(leren.huisstijl_prompt()) == ""
    assert api.post(f"/api/v1/leren/regel/{v['id']}", headers=A, json={"status": "actief"}).status_code == 200
    # Een andere arts kan andermans regel niet zien of aanzetten.
    assert api.post(f"/api/v1/leren/regel/{v['id']}", headers=B, json={"status": "afgewezen"}).status_code == 404
    assert api.get("/api/v1/leren/overzicht", headers=B).json()["regels"] == []
    leren._cache.clear()

    gezien = []
    monkeypatch.setattr(llm_service, "complete", nep_llm({"s": "x", "o": "", "e": "", "p": ""}, gezien))
    leren.zet_eigenaar("naam:dr_a")
    asyncio.run(pipeline.genereer_soep("Arts: hallo", "mistral"))
    assert "HUISSTIJL VAN DEZE ARTS" in gezien[0]["user"] and "li en re" in gezien[0]["user"]
    leren.zet_eigenaar("naam:dr_b")
    asyncio.run(pipeline.genereer_soep("Arts: hallo", "mistral"))
    assert "HUISSTIJL" not in gezien[1]["user"]


def test_woord_gaat_vanzelf_mee_na_drie_keer(api, monkeypatch):
    monkeypatch.setattr(llm_service, "complete", nep_llm({"regels": [], "woorden": [{"van": "meta prolol", "naar": "metoprolol"}]}))
    for i in range(3):
        api.post("/api/v1/leren/soep", headers=A, json={"concept": CONCEPT, "definitief": DEFINITIEF})
    woorden = [r for r in api.get("/api/v1/leren/overzicht", headers=A).json()["regels"] if r["soort"] == "woord"]
    assert woorden[0]["status"] == "actief" and woorden[0]["aantal"] == 3
    leren.zet_eigenaar("naam:dr_a")
    leren._cache.clear()
    assert asyncio.run(leren.woordenlijst()) == ["metoprolol"]
    assert "meta prolol → metoprolol" in asyncio.run(leren.huisstijl_prompt())
    assert leren.met_woorden(["metoprolol"], "geen lijst") == ["metoprolol"]
    assert leren.met_woorden(["metoprolol"], ["Lasègue"]) == ["metoprolol", "Lasègue"]


def test_zelf_toevoegen_afwijzen_en_weghalen(api):
    r = api.post("/api/v1/leren/regel", headers=A, json={"soort": "woord", "van": "furabit", "naar": "Furabid"})
    assert r.status_code == 200 and r.json()["status"] == "actief"
    assert api.post("/api/v1/leren/regel", headers=A, json={"soort": "soep", "regel": "kort"}).status_code == 400
    t = api.post("/api/v1/leren/regel", headers=A, json={"soort": "tolk", "taal": "ar-MA",
                                                          "regel": "Zeg voor bloeddruk in het Darija: tension."}).json()
    assert t["taal"] == "ar-MA"
    assert api.post(f"/api/v1/leren/regel/{t['id']}", headers=A, json={"status": "weg"}).status_code == 200
    regels = api.get("/api/v1/leren/overzicht", headers=A).json()["regels"]
    assert [r["soort"] for r in regels] == ["woord"]


def test_tolk_leert_van_eenvoudiger_en_neemt_afspraken_mee(api, monkeypatch):
    gezien = []
    monkeypatch.setattr(llm_service, "complete", nep_llm({"regels": ["Zeg voor 'hypertensie' in het Darija: tension (الطونسيون)."]}, gezien))
    d = api.post("/api/v1/leren/tolk", headers=A, json={"taal": "ar-MA", "beurten": 8, "weggehaald": 1,
        "eenvoudiger": [{"voor": "عندك ارتفاع ضغط الدم", "na": "عندك الطونسيون"}]}).json()
    assert d["voorstellen"][0]["soort"] == "tolk" and d["voorstellen"][0]["taal"] == "ar-MA"
    assert "Darija" in gezien[0]["system"] or "Marokkaans" in gezien[0]["system"]
    api.post(f"/api/v1/leren/regel/{d['voorstellen'][0]['id']}", headers=A, json={"status": "actief"})
    leren._cache.clear()
    leren.zet_eigenaar("naam:dr_a")
    system, _ = tolk.vertaal_prompts("Heeft u hoge bloeddruk?", "arts", tolk.TALEN["ar-MA"], [],
                                     afspraken=asyncio.run(leren.tolk_prompt("ar-MA")))
    assert "AFSPRAKEN VAN DEZE ARTS" in system and "tension" in system
    assert asyncio.run(leren.tolk_prompt("tr")) == ""
    m = [x for x in api.get("/api/v1/leren/overzicht", headers=A).json()["meting"] if x["soort"] == "tolk"][0]
    assert m["eenvoudiger"] == 1 and m["weggehaald"] == 1


def test_gewijzigd_pct():
    assert leren.gewijzigd_pct(CONCEPT, CONCEPT) == 0.0
    assert 0 < leren.gewijzigd_pct(CONCEPT, DEFINITIEF) < 60
    assert leren.schoon("Noteer 12-03-1961 altijd") == ""


def test_econsult_stijl_leren_goedkeuren_en_meegeven(api, monkeypatch):
    from services.cloud_api import econsult
    concept = "Beste [naam patiënt],\n\nU kunt paracetamol gebruiken.\n\nMet vriendelijke groet,\n[Naam huisarts]"
    verstuurd = "Goedemorgen,\n\nU kunt paracetamol gebruiken. Bel ons als het niet beter gaat.\n\nHartelijke groet,\nDokter A"
    antwoord = {"regels": ["Begin met 'Goedemorgen,' in plaats van 'Beste'.", "Sluit af met 'Hartelijke groet,'.",
                           "Noem bij patiënt J. de Vries 12-03-2024 iets"]}
    gezien = []
    monkeypatch.setattr(llm_service, "complete", nep_llm(antwoord, gezien))
    r = api.post("/api/v1/leren/econsult", headers=A, json={"concept": concept, "definitief": verstuurd})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["gewijzigd_pct"] > 2
    # a rule with a date never becomes a proposal
    assert [v["soort"] for v in d["voorstellen"]] == ["econsult", "econsult"]
    assert "Alleen vorm, toon en opbouw" in gezien[0]["system"]
    # not yet approved: not in the prompt
    assert asyncio.run(leren.econsult_prompt()) == ""
    for v in d["voorstellen"]:
        assert api.post(f"/api/v1/leren/regel/{v['id']}", headers=A, json={"status": "actief"}).status_code == 200
    # the e-consult prompt of dr A carries the style, dr B's does not
    seen = []
    monkeypatch.setattr(econsult.llm_service, "complete", nep_llm({
        "bericht": "", "vraag_kort": "", "feiten": [], "nhg": {"richtlijn": "", "punten": [], "alarm": [],
        "schriftelijk_geschikt": True}, "antwoord": "x", "journaal": "", "let_op": ""}, seen))
    dossier = "PATIËNT: J.J.\n== JOURNAAL ==\n12-03-2024 K78 Atriumfibrilleren."
    assert api.post("/api/v1/econsult/concept", headers=A, json={"dossier": dossier}).status_code == 200
    assert api.post("/api/v1/econsult/concept", headers=B, json={"dossier": dossier}).status_code == 200
    assert "Goedemorgen" in seen[0]["system"] and "SCHRIJFSTIJL VAN DEZE ARTS" in seen[0]["system"]
    assert "SCHRIJFSTIJL" not in seen[1]["system"]
    # in the overview, and can be added by hand
    soorten = [x["soort"] for x in api.get("/api/v1/leren/overzicht", headers=A).json()["regels"]]
    assert soorten.count("econsult") == 2
    assert api.post("/api/v1/leren/regel", headers=B, json={"soort": "econsult", "regel": "Spreek de patiënt aan met je."}).status_code == 200


def test_econsult_weinig_veranderd_alleen_meten(api, monkeypatch):
    gezien = []
    monkeypatch.setattr(llm_service, "complete", nep_llm({"regels": ["x"]}, gezien))
    t = "Beste [naam patiënt],\n\nU kunt paracetamol gebruiken.\n\nMet vriendelijke groet,\n[Naam huisarts]"
    d = api.post("/api/v1/leren/econsult", headers=A, json={"concept": t, "definitief": t}).json()
    assert d == {"gewijzigd_pct": 0.0, "voorstellen": []} and gezien == []
