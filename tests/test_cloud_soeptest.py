"""SOEP-test: the same conversation to Claude and the EU model, with a fabrication check."""

import json

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import beheer, main, pipeline, register, soeptest
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    async def aan():
        return True
    monkeypatch.setattr(beheer, "testgereedschap_aan", aan)   # the admin switch in Beheer, off by default
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


def test_testgereedschap_is_off_unless_switched_on(monkeypatch):
    """Until an administrator switches them on in Beheer the test tools are not
    there: 404 for everyone, also for an administrator, and nothing reaches a
    provider. Without a register the switch cannot be on."""
    monkeypatch.undo()
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gezien = []

    async def fake_soep(*a, **kw):
        gezien.append(1)
        raise AssertionError("geen model-aanroep als het testgereedschap uit staat")

    monkeypatch.setattr(pipeline, "genereer_soep", fake_soep)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test"
    try:
        api = TestClient(main.app)
        for r in (api.get("/api/v1/beheer/testset"),
                  api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn"}),
                  api.post("/api/v1/beheer/testset/inzending", json={"titel": "Knie", "gesprek": "Spreker 1: x" * 50}),
                  api.post("/api/v1/beheer/spraaktest", files={"audio": ("x.webm", b"0" * 5000)}),
                  api.get("/beheer/spraaktest")):
            assert r.status_code == 404 and "Beheer" in r.text, r.text
        assert gezien == []
    finally:
        main.app.dependency_overrides.clear()


def test_beheerder_zet_testgereedschap_aan_en_uit(monkeypatch):
    """The switch in Beheer: stored in vs_instellingen, read by the test tools,
    and every change logged with the administrator's name."""
    monkeypatch.undo()                       # the real switch, not the fixture's
    monkeypatch.setenv("API_KEYS", "geheim")
    opslag, logs = {}, []
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")

    async def execute(query, *args):
        if "vs_instellingen" in query:
            opslag[args[0]] = args[1]
        return "OK"

    async def fetch(query, *args):
        return [{"sleutel": k, "waarde": v} for k, v in opslag.items()]

    async def fetchrow(query, *args):
        return {"waarde": opslag[args[0]]} if args[0] in opslag else None

    async def log(door, handeling, praktijk_id=None, **details):
        logs.append((door, handeling))

    monkeypatch.setattr(register, "execute", execute)
    monkeypatch.setattr(register, "fetch", fetch)
    monkeypatch.setattr(register, "fetchrow", fetchrow)
    monkeypatch.setattr(register, "log", log)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "dr-test"
    try:
        api = TestClient(main.app)
        assert api.get("/api/v1/beheer/instellingen").json()["testgereedschap"] is False
        assert api.get("/api/v1/beheer/testset").status_code == 404
        r = api.put("/api/v1/beheer/instellingen", json={"testgereedschap": True})
        assert r.status_code == 200 and r.json()["testgereedschap"] is True
        assert api.get("/api/v1/beheer/testset").status_code == 200
        r = api.put("/api/v1/beheer/instellingen", json={"testgereedschap": False})
        assert r.json()["testgereedschap"] is False
        assert api.get("/api/v1/beheer/testset").status_code == 404
        assert ("dr-test", "testgereedschap.aan") in logs and ("dr-test", "testgereedschap.uit") in logs
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
    assert r["totaal"] == 8 and r["gehaald"] == 6
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
        return [{"probleem": 0, "veld": "o", "tekst": "PSIS-gebied", "reden": "niet gezegd"}]

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
        # nothing removed: the same report, with the markings next to it
        assert g["problemen"] == d["eu"]["problemen"] and g["markeringen"][0]["tekst"] == "PSIS-gebied"

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
                                   "e": "Aspecifieke lage rugpijn", "p": "Paracetamol max 6 dd (3x2)"}], rug)
    assert r["fout"] == ["drukpijn op de wervelkolom (die was juist niet pijnlijk; wel paravertebraal)"]
    assert soeptest.toets_valkuilen([{"s": "hernia, werk", "p": "Paracetamol 4dd 2"}], rug)["fout"]
    borst = soeptest.toets_valkuilen([{"o": "Drukpijn op ribben bij borstbeen links (3 punten)", "e": "Tietze-syndroom",
                                       "p": "scan niet nodig; terugkomen bij zorgen"}], idx["03-pijn-op-de-borst"]["toets"])
    # "links" is right here (visible in the video); Tietze is not
    assert not any("zijde" in f for f in borst["fout"]) and any("Tietze" in f for f in borst["fout"])
    moe = idx["04-moeheid"]["toets"]
    r = soeptest.toets_valkuilen([{"s": "bezorgd over oorzaak (schildklier, bloedarmoede, nieren)",
                                   "o": "veel energie-kostende activiteiten", "e": "Moeheid",
                                   "p": "geen bloedonderzoek; controle over 4-6 weken"}], moe)
    assert r["fout"] == ["bloedarmoede of nieren als zorg van de patiënt (noemde de arts)"]


def test_control_pass_only_marks_and_never_changes_the_report():
    enkel = pipeline.SOEPResult(problemen=[{
        "s": "Pijn li enkel na badminton.",
        "o": "li enkel licht gezwollen t.o.v. re; drukpijn laterale malleolus li; bewegingen pijnlijk.",
        "e": "Enkelverzwikking li zonder aanwijzingen voor fractuur of artrose/reuma",
        "p": "Paracetamol bij pijn. Vangnet: bij toename klachten terugkomen.",
        "icpc_code": "L77", "icpc_titel": "Distorsie enkel"}])
    voor = json.dumps(enkel.problemen)
    mark = pipeline.markeringen_uit(enkel, {"schrappen": [
        {"veld": "o", "tekst": "laterale malleolus", "reden": "plaats niet genoemd"},
        {"veld": "p", "tekst": "Vangnet: bij toename klachten terugkomen."},
        {"veld": "o", "tekst": "staat er niet in"}, {"veld": "x", "tekst": "li"}, {"probleem": 7, "veld": "o", "tekst": "li"}],
        "hulpvraag": "wil weten of het artrose is"})
    assert json.dumps(enkel.problemen) == voor
    assert [(m["veld"], m["tekst"]) for m in mark] == [("o", "laterale malleolus"), ("p", "Vangnet: bij toename klachten terugkomen."), ("s", "")]
    assert "hulpvraag ontbreekt mogelijk" in mark[-1]["reden"] and "geknipt" not in mark[0]


def test_fair_pitfalls_catch_what_cutting_broke():
    idx = {c["id"]: c for c in soeptest.index()}
    kapot_enkel = [{"s": "li enkel, vraagt naar artrose of reuma", "o": "Drukpijn. pijnlijk.",
                    "e": "Enkelverzwikking li artrose/reuma", "p": "Paracetamol", "icpc_code": "L77", "icpc_titel": "Distorsie"}]
    r = soeptest.toets_valkuilen(kapot_enkel, idx["02-verzwikte-enkel"]["toets"])
    assert any("artrose of reuma als diagnose" in f for f in r["fout"])
    leeg = [{"s": "li enkel, artrose?", "o": "", "e": "", "p": "Paracetamol", "icpc_code": "L77", "icpc_titel": ""}]
    assert "E is leeg" in soeptest.toets_valkuilen(leeg, idx["02-verzwikte-enkel"]["toets"])["fout"]
    goed = [{"s": "li enkel, artrose of reuma?", "o": "drukpijn", "e": "Distorsie li enkel, geen aanwijzingen voor artrose of reuma",
             "p": "Paracetamol", "icpc_code": "L77", "icpc_titel": "Distorsie"}]
    assert soeptest.toets_valkuilen(goed, idx["02-verzwikte-enkel"]["toets"])["fout"] == []
    # chest: the scan decision has to be in P, not only the question in S
    borst = [{"s": "vraagt om scan", "o": "RR normaal", "e": "Geen aanwijzingen voor cardiale oorzaak.",
              "p": "Uitleg; gaat vanzelf over.", "icpc_code": "L04", "icpc_titel": ""}]
    f = soeptest.toets_valkuilen(borst, idx["03-pijn-op-de-borst"]["toets"])["fout"]
    assert any("scan" in x for x in f) and any("drukpijn" in x for x in f) and any("werkdiagnose" in x for x in f)
    assert "afgebroken zin (er is iets uit geknipt)" in soeptest.verdacht(
        [{"s": "Klachten: en soms onder de borst; tijgerbalsem (, maar klachten blijven)"}], "Spreker 1: x")
    assert not any("afgebroken" in x for x in soeptest.verdacht([{"o": "li enkel t.o.v. re; drukpijn li"}], "Spreker 1: li re"))


def test_false_positives_from_the_large_run():
    rug = soeptest.gesprek_uit_testset("01-lage-rugpijn")
    v = soeptest.verdacht([{"s": "ontstaan bij draaibeweging met zwaar gewicht in handen"}], rug)
    assert not any("gewichtsverlies" in x for x in v)
    borst = soeptest.gesprek_uit_testset("03-pijn-op-de-borst")
    assert not soeptest.verdacht([{"s": "hulpvraag is of dit kan worden uitgesloten"}], borst)
    from services.cloud_api import icpc_controle
    assert "L03" in icpc_controle.controleer("L02", "Lage rugpijn met uitstraling")


@pytest.mark.asyncio
async def test_controleer_soep_sends_the_report_and_returns_markings(monkeypatch):
    gezien = {}

    async def complete(**k):
        gezien.update(k)
        return json.dumps({"schrappen": [{"probleem": 0, "veld": "o", "tekst": "(stopt halverwege)"}], "hulpvraag": ""})

    from services.cloud_api import llm_service
    monkeypatch.setattr(llm_service, "complete", complete)
    soep = pipeline.SOEPResult(problemen=[{"s": "Hulpvraag: hernia?", "o": "anteflexie beperkt (stopt halverwege)",
                                           "e": "", "p": "", "icpc_code": "L03", "icpc_titel": "Lage rugpijn"}])
    mark = await pipeline.controleer_soep("Spreker 1: ...", soep, "mistral", model="mistral-large-latest")
    assert mark == [{"probleem": 0, "veld": "o", "tekst": "(stopt halverwege)", "reden": ""}]
    assert soep.problemen[0]["o"] == "anteflexie beperkt (stopt halverwege)"
    assert gezien["model"] == "mistral-large-latest" and "schrappen" in json.dumps(gezien["json_schema"])
    assert "stopt halverwege" in gezien["user_prompt"]


def test_soep_prompt_asks_for_the_decision_on_a_requested_test():
    from services.cloud_api import prompts
    assert "scan" in prompts.SOEP_SYSTEM_PROMPT and "besluit van de arts" in prompts.SOEP_SYSTEM_PROMPT


def test_testset_reports_go_to_the_log_but_own_conversations_do_not(monkeypatch):
    from structlog.testing import capture_logs

    async def fake_soep(gesprek, aanbieder=None, taal=None, model=None):
        return pipeline.SOEPResult(problemen=[{"s": "rugpijn", "o": "", "e": "Lage rugpijn", "p": "Paracetamol",
                                               "icpc_code": "L03", "icpc_titel": "Lage rugpijn"}])

    async def log(*a, **k):
        pass

    monkeypatch.setattr(pipeline, "genereer_soep", fake_soep)
    monkeypatch.setattr(register, "log", log)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test"
    try:
        api = TestClient(main.app)
        with capture_logs() as logs:
            assert api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn", "run": "run-20261003T0100.1"}).status_code == 200
        rap = [x for x in logs if x["event"] == "soeptest.rapport"]
        assert [x["rol"] for x in rap] == ["claude", "eu"] and rap[0]["run"] == "run-20261003T0100.1"
        assert "Paracetamol" in rap[0]["verslag"] and rap[0]["valkuilen"]["totaal"] > 0
        with capture_logs() as logs:
            api.post("/api/v1/beheer/soeptest", json={"gesprek": "Spreker 1: keelpijn sinds gisteren"})
        assert not [x for x in logs if x["event"] == "soeptest.rapport"]
        assert api.post("/api/v1/beheer/soeptest", json={"id": "01-lage-rugpijn", "run": "x; drop"}).status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_submission_goes_to_the_log_in_parts(monkeypatch):
    from structlog.testing import capture_logs
    audit = []

    async def log(door, handeling, praktijk_id=None, **details):
        audit.append(details)

    monkeypatch.setattr(register, "log", log)
    gesprek = "Spreker 1: " + "ik heb last van mijn knie. " * 300
    api = TestClient(main.app)
    assert api.post("/api/v1/beheer/testset/inzending", json={"titel": "Knie", "gesprek": gesprek}).status_code in (401, 403, 503)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test"
    try:
        with capture_logs() as logs:
            d = api.post("/api/v1/beheer/testset/inzending",
                         json={"titel": "Knie", "bron": "https://youtu.be/x", "gesprek": gesprek}).json()
        delen = [x for x in logs if x["event"] == "testset.inzending"]
        assert d["delen"] == len(delen) > 1 and "".join(x["tekst"] for x in delen) == gesprek
        assert all(x["inzending"] == d["id"] for x in delen) and "tekst" not in str(audit)
        assert api.post("/api/v1/beheer/testset/inzending", json={"titel": "Kort", "gesprek": "te kort"}).status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_lessons_from_the_marking_run():
    # ordinary Dutch is not a broken sentence
    for zin in ("Gebruikt paracetamol voor de nacht. Zorgen: of het artrose is", "komen er niet meer van. Pt",
                "pt is hier bang voor.\nDrukpijn"):
        assert not any("afgebroken" in x for x in soeptest.verdacht([{"s": zin}], "Spreker 1: x")), zin
    from services.cloud_api import icpc_controle
    assert icpc_controle.controleer("L77", "Distorsie/verstuiking") is None



def test_truncated_consult_case_catches_an_invented_second_half():
    idx = {c["id"]: c for c in soeptest.index()}
    toets = idx["05-lage-rugpijn-afgebroken"]["toets"]
    gesprek = soeptest.gesprek_uit_testset("05-lage-rugpijn-afgebroken")
    assert "wervelkolom" not in gesprek and "optillen" not in gesprek.lower()   # stops before the exam
    verzonnen = [{"s": "Hulpvraag: hernia? Werk kinderdagverblijf.",
                  "o": "LO: geen standsafwijking. Drukpijn onderrug re. Lasègue neg. Kracht re been 5/5.",
                  "e": "Aspecifieke lage rugpijn, geen aanwijzingen voor hernia",
                  "p": "Paracetamol, evt. ibuprofen 3dd 400 mg. Controle bij mictie/defecatiestoornissen.",
                  "icpc_code": "L03", "icpc_titel": "Lage rugpijn"}]
    eerlijk = [{"s": "Hulpvraag: uitsluiten hernia; veilig werken met kinderen?", "o": "niet in de opname",
                "e": "niet in de opname", "p": "niet in de opname", "icpc_code": "L03", "icpc_titel": "Lage rugpijn"}]
    assert soeptest.toets_valkuilen(eerlijk, toets)["fout"] == []
    r = soeptest.toets_valkuilen(verzonnen, toets)
    assert r["gehaald"] <= r["totaal"] - 5
    v = soeptest.verdacht(verzonnen, gesprek)
    assert any("Lasègue" in x for x in v) and any("5/5" in x for x in v) and any("cauda" in x for x in v)


def test_version_header_is_logged_and_min_version_published(monkeypatch):
    from services.cloud_api import data_policy
    monkeypatch.setenv("API_KEYS", "geheim")
    get_config.cache_clear()
    api = TestClient(main.app)
    d = api.get("/api/v1/providers", headers={"X-API-Key": "geheim", "X-VitaScribe-Versie": "2.15.3"}).json()
    assert d["min_versie"] == data_policy.MIN_EXTENSIE_VERSIE
    t = data_policy.zet_versie("2.15.3; drop")
    assert data_policy.versie() == ""
    data_policy.herstel_versie(t)
