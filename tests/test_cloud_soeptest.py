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
    assert "hoeveelheid niet in het gesprek: 500mg" in v
    assert soeptest.verdacht([{"p": "Paracetamol 3dd2, max 6 per dag", "o": "drukpijn rechts"}], rug) == []
    enkel = soeptest.gesprek_uit_testset("02-verzwikte-enkel")
    assert "plaats niet in het gesprek: lateraal" in soeptest.verdacht([{"o": "drukpijn li lateraal"}], enkel)
    borst = soeptest.gesprek_uit_testset("03-pijn-op-de-borst")
    v = soeptest.verdacht([{"e": "cardiale oorzaak uitgesloten", "o": "RR 120/80"}], borst)
    assert any("120/80" in x for x in v) and any("uitgesloten" in x for x in v)
    assert "zijde niet in het gesprek: rechts" in soeptest.verdacht([{"o": "pijn rechts"}], "Spreker 1: pijn links")


def test_soeptest_endpoint(monkeypatch):
    gezien = []

    async def fake_soep(gesprek, aanbieder=None, taal=None, model=None):
        gezien.append((aanbieder, model))
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
        assert sorted(gezien) == [("anthropic", None), ("mistral", None)] and d["eu_model"] == "mistral-large-latest"
        assert d["claude"]["verdacht"] == []
        assert "hoeveelheid niet in het gesprek: 500mg" in d["eu"]["verdacht"]
        assert d["valkuilen"]
        # the pitfalls of the consult as a hard check
        assert d["eu"]["valkuilen"]["gehaald"] < d["eu"]["valkuilen"]["totaal"]
        assert any("sterkte" in f for f in d["eu"]["valkuilen"]["fout"])
        gezien.clear()
        d = api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn", "eu_model": "medium"}).json()
        assert ("mistral", "mistral-medium-latest") in gezien and d["eu_model"] == "mistral-medium-latest"
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


def test_broader_fabrication_check_and_icpc():
    rug = soeptest.gesprek_uit_testset("01-lage-rugpijn")
    v = soeptest.verdacht([{"o": "drukpijn paravertebraal L4-L5, PSIS-gebied, Lasègue beiderzijds negatief",
                            "p": "Paracetamol 4dd 500 mg"}], rug)
    assert "wervelniveau niet in het gesprek: L4-L5" in v and "anatomisch punt niet in het gesprek: PSIS" in v
    assert any(x.startswith("frequentie") for x in v)
    # "aan allebei de kanten" in this consult: then "beiderzijds" is not flagged here (the pitfall test catches it)
    assert "beiderzijds niet in het gesprek" in soeptest.verdacht([{"o": "Lasègue beiderzijds negatief"}], "Spreker 1: been optillen")
    enkel = soeptest.gesprek_uit_testset("02-verzwikte-enkel")
    assert "vangnet of controle niet in het gesprek afgesproken" in soeptest.verdacht([{"p": "Terugkomen indien geen verbetering."}], enkel)
    borst = soeptest.gesprek_uit_testset("03-pijn-op-de-borst")
    assert soeptest.verdacht([{"p": "Terugkomen bij aanhoudende zorgen"}], borst) == []   # was agreed
    from services.cloud_api import icpc_controle
    assert "L02 is rugklachten" in icpc_controle.controleer("L02", "Pijn borstwand/ribben")
    assert icpc_controle.controleer("L04", "Pijn/symptomen thorax") is None
    assert icpc_controle.controleer("L77", "Enkelverzwikking/distorsie") is None
    assert icpc_controle.controleer("X99", "wat dan ook") is None     # not in the table: not judged


def test_pitfalls_score_the_first_run_reports():
    idx = {c["id"]: c for c in soeptest.index()}
    claude_enkel = [{"s": "linker enkel; vraagt of het artrose of reuma is", "o": "Drukpijn lateraal. Op rechter been wel.",
                     "e": "Distorsie li enkel, geen aanwijzingen voor artrose of reuma", "p": "Terugkomen indien geen verbetering.",
                     "icpc_code": "L77", "icpc_titel": "Verstuiking enkel"}]
    r = soeptest.toets_valkuilen(claude_enkel, idx["02-verzwikte-enkel"]["toets"])
    assert r["totaal"] == 6 and r["gehaald"] == 3
    mistral_moe = [{"s": "moeheid", "e": "overspanning", "p": "controle 4-6 weken", "icpc_code": "P78", "icpc_titel": "overspanning"}]
    r = soeptest.toets_valkuilen(mistral_moe, idx["04-moeheid"]["toets"])
    assert any("psychisch label" in f for f in r["fout"]) and any("schildklier" in f for f in r["fout"])


def test_undiscussed_topics_and_large_run_details():
    moe = soeptest.gesprek_uit_testset("04-moeheid")
    v = soeptest.verdacht([{"s": "moe", "o": "Geen suïcidegedachten."}], moe)
    assert "onderwerp niet besproken: suïcidaliteit" in v or any("suïcidaliteit" in x for x in v)
    assert not any("suïcidaliteit" in x for x in soeptest.verdacht([{"s": "moe"}], moe))
    enkel = soeptest.gesprek_uit_testset("02-verzwikte-enkel")
    assert any("lateralis" in x for x in soeptest.verdacht([{"o": "drukpijn malleolus lateralis"}], enkel))
    idx = {c["id"]: c for c in soeptest.index()}
    rug = [{"s": "rugpijn", "o": "Flexie: vingers tot halverwege de knie.", "e": "Lage rugpijn",
            "p": "Paracetamol 6dd", "icpc_code": "L03", "icpc_titel": "Lage rugpijn"}]
    r = soeptest.toets_valkuilen(rug, idx["01-lage-rugpijn"]["toets"])
    assert r["gehaald"] < r["totaal"]
    # "veel energie" in a normal sentence is not a psychological label
    r = soeptest.toets_valkuilen([{"s": "heeft niet meer heel veel energie", "e": "Moeheid", "p": "bloedonderzoek",
                                   "icpc_code": "A04", "icpc_titel": "Moeheid/zwakte"}], idx["04-moeheid"]["toets"])
    assert not any("energie" in f for f in r["fout"])


def test_soeptest_control_pass(monkeypatch):
    async def fake_soep(gesprek, aanbieder=None, taal=None, model=None):
        return pipeline.SOEPResult(problemen=[{"s": "rugpijn", "o": "PSIS-gebied drukpijn", "e": "Lage rugpijn",
                                               "p": "Paracetamol 6dd500mg", "icpc_code": "L03", "icpc_titel": ""}])

    gecontroleerd = []

    async def fake_controle(gesprek, soep, llm_provider=None, model=None):
        gecontroleerd.append((llm_provider, model, soep.problemen[0]["p"]))
        return pipeline.SOEPResult(problemen=[{"s": "rugpijn", "o": "drukpijn", "e": "Lage rugpijn",
                                               "p": "Paracetamol", "icpc_code": "L03", "icpc_titel": ""}])

    async def log(*a, **k):
        pass

    monkeypatch.setattr(pipeline, "genereer_soep", fake_soep)
    monkeypatch.setattr(pipeline, "controleer_soep", fake_controle)
    monkeypatch.setattr(register, "log", log)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test"
    try:
        api = TestClient(main.app)
        d = api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn"}).json()
        assert "eu_gecontroleerd" not in d and not gecontroleerd
        d = api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn", "controle": True}).json()
        assert gecontroleerd == [("mistral", None, "Paracetamol 6dd500mg")]
        g = d["eu_gecontroleerd"]
        assert d["eu"]["verdacht"] and g["verdacht"] == []
        assert g["valkuilen"]["gehaald"] > d["eu"]["valkuilen"]["gehaald"]

        async def kapot(*a, **k):
            raise RuntimeError("weg")
        monkeypatch.setattr(pipeline, "controleer_soep", kapot)
        d = api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn", "controle": True}).json()
        assert d["eu_gecontroleerd"]["fout"] == "RuntimeError" and "problemen" in d["eu"]
    finally:
        main.app.dependency_overrides.clear()


def test_control_prompt_keeps_the_rules():
    from services.cloud_api import prompts
    t = prompts.SOEP_CONTROLE_SYSTEM_PROMPT.lower()
    assert "schrap" in t and "hulpvraag" in t
    prompts.SOEP_CONTROLE_USER_TEMPLATE.format(transcript="x", soep="{}")


def test_pitfalls_score_the_medium_run_reports():
    idx = {c["id"]: c for c in soeptest.index()}
    rug = idx["01-lage-rugpijn"]["toets"]
    r = soeptest.toets_valkuilen([{"s": "hernia; werken met kinderen", "o": "Drukpijn wervelkolom onderrug, re meer dan li.",
                                   "p": "Paracetamol max 6 dd (3x2)"}], rug)
    assert r["fout"] == ["drukpijn op de wervelkolom (die was juist niet pijnlijk; wel paravertebraal)"]
    assert soeptest.toets_valkuilen([{"s": "hernia, werk", "p": "Paracetamol 4dd 2"}], rug)["fout"]
    borst = soeptest.toets_valkuilen([{"o": "Drukpijn op ribben bij borstbeen links (3 punten)", "e": "Tietze-syndroom",
                                       "p": "scan niet nodig; terugkomen bij zorgen"}], idx["03-pijn-op-de-borst"]["toets"])
    # "links" is right here (visible in the video); Tietze is not
    assert not any("zijde" in f for f in borst["fout"]) and any("Tietze" in f for f in borst["fout"])
    moe = idx["04-moeheid"]["toets"]
    r = soeptest.toets_valkuilen([{"s": "bezorgd over oorzaak (schildklier, bloedarmoede, nieren)",
                                   "o": "veel energie-kostende activiteiten", "p": "controle over 4-6 weken"}], moe)
    assert r["fout"] == ["bloedarmoede of nieren als zorg van de patiënt (noemde de arts)"]


def test_control_pass_can_only_cut():
    enkel = pipeline.SOEPResult(problemen=[{
        "s": "Pijn li enkel na badminton.",
        "o": "li enkel licht gezwollen t.o.v. re; drukpijn malleolus lateralis li; bewegingen pijnlijk, met name dorsaalflexie; geen hematoom.",
        "e": "Distorsie li enkel.", "p": "Paracetamol bij pijn. Controle bij persisterende klachten na 2 wk.",
        "icpc_code": "L77", "icpc_titel": "Distorsie enkel"}])
    na = pipeline.pas_schrappingen_toe(enkel, {"schrappen": [
        {"veld": "o", "tekst": "malleolus lateralis "}, {"veld": "o", "tekst": ", met name dorsaalflexie"},
        {"veld": "o", "tekst": "geen hematoom."}, {"veld": "p", "tekst": "Controle bij persisterende klachten na 2 wk."},
        {"veld": "o", "tekst": "staat er niet in"}, {"veld": "s", "tekst": "Hulpvraag: x"}, {"veld": "x", "tekst": "li"},
        {"probleem": 7, "veld": "o", "tekst": "li"}],
        "hulpvraag": "wil weten of het artrose of reuma is"})
    d = na.problemen[0]
    assert d["o"] == "li enkel licht gezwollen t.o.v. re; drukpijn li; bewegingen pijnlijk"
    assert "malleolus" not in d["o"] and "hematoom" not in d["o"] and d["p"] == "Paracetamol bij pijn."
    assert d["s"] == "Pijn li enkel na badminton. Hulpvraag: wil weten of het artrose of reuma is"
    assert d["icpc_code"] == "L77" and d["icpc_titel"] == "Distorsie enkel"
    # every word after the pass was already in the first report, apart from the request for help
    voor = set(" ".join(enkel.problemen[0][k] for k in "sop").lower().split())
    assert set(" ".join(d[k] for k in "op").lower().split()) <= voor | {"pijn.", "li;", "pijnlijk"}


def test_false_positives_from_the_large_run():
    rug = soeptest.gesprek_uit_testset("01-lage-rugpijn")
    v = soeptest.verdacht([{"s": "ontstaan bij draaibeweging met zwaar gewicht in handen"}], rug)
    assert not any("gewichtsverlies" in x for x in v)
    borst = soeptest.gesprek_uit_testset("03-pijn-op-de-borst")
    assert not soeptest.verdacht([{"s": "hulpvraag is of dit kan worden uitgesloten"}], borst)
    from services.cloud_api import icpc_controle
    assert "L03" in icpc_controle.controleer("L02", "Lage rugpijn met uitstraling")


@pytest.mark.asyncio
async def test_controleer_soep_sends_the_report_and_applies_the_cuts(monkeypatch):
    gezien = {}

    async def complete(**k):
        gezien.update(k)
        return json.dumps({"schrappen": [{"probleem": 0, "veld": "o", "tekst": " (stopt halverwege)"}], "hulpvraag": ""})

    from services.cloud_api import llm_service
    monkeypatch.setattr(llm_service, "complete", complete)
    soep = pipeline.SOEPResult(problemen=[{"s": "Hulpvraag: hernia?", "o": "anteflexie beperkt (stopt halverwege)",
                                           "e": "", "p": "", "icpc_code": "L03", "icpc_titel": "Lage rugpijn"}])
    na = await pipeline.controleer_soep("Spreker 1: ...", soep, "mistral", model="mistral-large-latest")
    assert na.problemen[0]["o"] == "anteflexie beperkt" and na.icpc_code == "L03"
    assert gezien["model"] == "mistral-large-latest" and "schrappen" in json.dumps(gezien["json_schema"])
    assert "stopt halverwege" in gezien["user_prompt"]


def test_soep_prompt_asks_for_the_decision_on_a_requested_test():
    from services.cloud_api import prompts
    assert "scan" in prompts.SOEP_SYSTEM_PROMPT and "besluit van de arts" in prompts.SOEP_SYSTEM_PROMPT
