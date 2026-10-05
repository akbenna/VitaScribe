"""Tolk: per beurt verstaan, vertalen en voorlezen; verslag uit de Nederlandse kant."""

import json

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import llm_service, main, pipeline, tolk
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("MISTRAL_API_KEY", "m")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "d")
    get_config.cache_clear()
    tolk._stemmen = None
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


H = {"X-API-Key": "geheim"}
EU = {**H, "X-VitaScribe-Modus": "eu"}


def nep_llm(antwoord, gezien):
    async def complete(system=None, user=None, provider=None, json_mode=False, max_tokens=None, cache_system=False,
                       quality=False, json_schema=None, model=None, system_prompt=None, user_prompt=None):
        system, user = system or system_prompt, user or user_prompt
        gezien.append(dict(system=system, user=user, provider=provider, json_mode=json_mode, schema=json_schema))
        return json.dumps(antwoord)
    return complete


def beurt(api, headers=H, **velden):
    data = {"spreker": "arts", "taal": "tr", "consent": "true", **velden}
    return api.post("/api/v1/tolk/beurt", headers=headers, data=data,
                    files={"audio": ("beurt.webm", b"geluid", "audio/webm")})


def test_talen_per_modus(api):
    claude = {t["code"]: t for t in api.get("/api/v1/tolk/talen", headers=H).json()["talen"]}
    eu = {t["code"]: t for t in api.get("/api/v1/tolk/talen", headers=EU).json()["talen"]}
    assert set(claude) == {"tr", "pl", "uk", "ar", "ar-SY", "ar-MA", "de", "fr", "en"}
    assert all(t["verstaat"] for t in claude.values())
    # Voxtral kent geen Turks, Pools of Oekraïens; Arabisch, Duits, Frans en Engels wel.
    assert [c for c, t in eu.items() if not t["verstaat"]] == ["tr", "pl", "uk"]
    assert "Voxtral" in eu["tr"]["waarom"]
    # Voorlezen door Mistral alleen in de talen van Voxtral TTS; de rest op de computer.
    assert claude["ar-MA"]["stem"] == "mistral" and claude["tr"]["stem"] == "computer"


def test_beurt_arts_naar_turks(api, monkeypatch):
    gezien, stt = [], []

    async def verstaan(audio, taal, sleutel, content_type="audio/webm"):
        stt.append((audio, taal.code, sleutel))
        return "Heeft u ook koorts gehad?"
    monkeypatch.setattr(tolk, "spraak_naar_tekst", verstaan)
    monkeypatch.setattr(llm_service, "complete", nep_llm(
        {"vertaling": "Ateşiniz de oldu mu?", "terugvertaling": "Heeft u ook koorts gehad?",
         "onzeker": False, "twijfel": ""}, gezien))
    eerder = json.dumps([{"spreker": "patient", "nl": "Ik hoest al een week."}])
    r = beurt(api, eerder=eerder)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["origineel"] == "Heeft u ook koorts gehad?" and d["vertaling"] == "Ateşiniz de oldu mu?"
    assert d["terugvertaling"] and d["leeg"] is False
    # De arts spreekt Nederlands: zo wordt het verstaan; met de Deepgram-sleutel (Claude-modus).
    assert stt == [(b"geluid", "nl", "d")]
    s = gezien[0]
    assert "van Nederlands naar Turks" in s["system"] and s["json_mode"] and s["provider"] == "anthropic"
    assert "Patiënt: Ik hoest al een week." in s["user"] and "GEZEGD DOOR DE ARTS" in s["user"]


def test_beurt_patient_in_eu_modus_gaat_naar_voxtral_en_mistral(api, monkeypatch):
    gezien, stt = [], []

    async def voxtral(audio, language=None, naam="", diarize=True):
        stt.append((language, diarize))
        from services.cloud_api.stt_service import TranscriptResult
        return TranscriptResult(raw_text="عندي وجع في بطني", provider="voxtral")
    monkeypatch.setattr(tolk.stt_service, "_transcribe_voxtral", voxtral)
    monkeypatch.setattr(llm_service, "complete", nep_llm(
        {"vertaling": "Ik heb pijn in mijn buik.", "terugvertaling": "x", "onzeker": False, "twijfel": ""}, gezien))
    r = beurt(api, headers=EU, spreker="patient", taal="ar-MA")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["vertaling"] == "Ik heb pijn in mijn buik."
    assert d["terugvertaling"] == ""          # naar het Nederlands: geen terugvertaling
    assert stt == [("ar", False)]             # Voxtral, Arabisch, zonder sprekerscheiding
    assert gezien[0]["provider"] == "mistral"
    assert "Darija" in gezien[0]["system"] and "naar Nederlands" in gezien[0]["system"]


def test_eu_modus_weigert_turkse_spraak_maar_wel_de_arts(api, monkeypatch):
    async def verstaan(audio, taal, sleutel, content_type="audio/webm"):
        return "Goedemorgen"
    monkeypatch.setattr(tolk, "spraak_naar_tekst", verstaan)
    monkeypatch.setattr(llm_service, "complete", nep_llm(
        {"vertaling": "Günaydın", "terugvertaling": "Goedemorgen", "onzeker": False, "twijfel": ""}, []))
    r = beurt(api, headers=EU, spreker="patient", taal="tr")
    assert r.status_code == 400 and "Turks" in r.json()["detail"]
    # De arts spreekt Nederlands: dat verstaat Voxtral; het vertalen naar het Turks kan het taalmodel.
    assert beurt(api, headers=EU, spreker="arts", taal="tr").status_code == 200


def test_beurt_zonder_toestemming_of_taal(api):
    assert beurt(api, consent="false").status_code == 400
    assert beurt(api, taal="nl").status_code == 400
    assert beurt(api, taal="xx").status_code == 400


def test_lege_beurt_kost_geen_vertaling(api, monkeypatch):
    async def stil(audio, taal, sleutel, content_type="audio/webm"):
        return ""
    gezien = []
    monkeypatch.setattr(tolk, "spraak_naar_tekst", stil)
    monkeypatch.setattr(llm_service, "complete", nep_llm({}, gezien))
    d = beurt(api).json()
    assert d["leeg"] is True and gezien == []


def test_eenvoudiger_met_tekst_zonder_opname(api, monkeypatch):
    gezien = []

    async def nooit(*a, **k):
        raise AssertionError("geen spraakherkenning bij opnieuw vertalen")
    monkeypatch.setattr(tolk, "spraak_naar_tekst", nooit)
    monkeypatch.setattr(llm_service, "complete", nep_llm(
        {"vertaling": "Ateşiniz var mı?", "terugvertaling": "Heeft u koorts?", "onzeker": False, "twijfel": ""}, gezien))
    r = api.post("/api/v1/tolk/beurt", headers=H, data={
        "spreker": "arts", "taal": "tr", "consent": "true", "eenvoudiger": "true", "tekst": "Heeft u koorts gehad?"})
    assert r.status_code == 200, r.text
    assert "eenvoudiger" in gezien[0]["system"]


def test_spreek_mistral_of_404(api, monkeypatch):
    async def stem(tekst, taal):
        return b"MP3" if taal.tts else None
    monkeypatch.setattr(tolk, "tekst_naar_spraak", stem)
    r = api.post("/api/v1/tolk/spreek", headers=H, json={"tekst": "مرحبا", "taal": "ar-MA"})
    assert r.status_code == 200 and r.content == b"MP3" and r.headers["content-type"] == "audio/mpeg"
    # Turks: geen stem bij Mistral; de extensie leest dan zelf voor.
    assert api.post("/api/v1/tolk/spreek", headers=H, json={"tekst": "Merhaba", "taal": "tr"}).status_code == 404


def test_kies_stem():
    stemmen = [{"id": "en_paul_neutral"}, {"id": "fr_marie_neutral"}, {"id": "x", "languages": ["ar-SA"]}]
    assert tolk.kies_stem(stemmen, "fr") == "fr_marie_neutral"
    assert tolk.kies_stem(stemmen, "ar") == "x"
    assert tolk.kies_stem(stemmen, "nl") == "en_paul_neutral"   # geen eigen stem: de eerste
    assert tolk.kies_stem([], "nl") is None


def test_verslag_uit_nederlandse_kant(api, monkeypatch):
    gezien = {}

    async def verwerk(transcript, llm_provider=None, bestandsgrootte="", taal=None, taalregel=None):
        gezien.update(tekst=transcript.raw_text, regel=taalregel)
        r = pipeline.PipelineResult()
        r.soep = pipeline.SOEPResult(s="Hoest sinds een week.")
        return r
    monkeypatch.setattr(pipeline, "verwerk_transcript", verwerk)
    r = api.post("/api/v1/tolk/verslag", headers=H, json={"taal": "tr", "consent": True, "beurten": [
        {"spreker": "arts", "nl": "Wat kan ik voor u doen?"},
        {"spreker": "patient", "nl": "Ik hoest al een week."},
        {"spreker": "patient", "nl": "Vooral 's nachts."},
        {"spreker": "arts", "nl": "Heeft u koorts gehad?"},
    ]})
    assert r.status_code == 200, r.text
    assert r.json()["soep"]["s"] == "Hoest sinds een week."
    assert gezien["tekst"] == ("Arts: Wat kan ik voor u doen?\n"
                               "Patiënt (vertaald): Ik hoest al een week. Vooral 's nachts.\n"
                               "Arts: Heeft u koorts gehad?")
    assert "Turks" in gezien["regel"] and "AI-tolk" in gezien["regel"]


def test_verslag_vraagt_toestemming(api):
    r = api.post("/api/v1/tolk/verslag", headers=H, json={"taal": "tr", "beurten": [{"spreker": "arts", "nl": "x"}]})
    assert r.status_code == 400


def test_genereer_soep_gebruikt_taalregel(monkeypatch):
    import asyncio
    gezien = []
    monkeypatch.setattr(llm_service, "complete", nep_llm({"s": "x", "o": "", "e": "", "p": ""}, gezien))
    asyncio.run(pipeline.genereer_soep("Arts: hallo", "mistral", taalregel="TOLKREGEL\n\n"))
    assert gezien[0]["user"].startswith("TOLKREGEL")
