"""Werkplan stap 6: Gladia en Speechmatics als Europese spraakdienst."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from services.cloud_api import beheer, data_policy, main, register, stt_service, tolk
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    monkeypatch.setenv("GLADIA_API_KEY", "gladia-test")
    monkeypatch.setenv("SPEECHMATICS_API_KEY", "sm-test")
    monkeypatch.delenv("EU_STT_PROVIDER", raising=False)
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _mock(monkeypatch, handler):
    echte = httpx.AsyncClient
    monkeypatch.setattr(stt_service.httpx, "AsyncClient",
                        lambda **kw: echte(transport=httpx.MockTransport(handler),
                                           **{k: v for k, v in kw.items() if k != "transport"}))

    async def snel(_):
        return None
    monkeypatch.setattr(asyncio, "sleep", snel)


def _gladia(log):
    polls = {"n": 0}

    def handler(request: httpx.Request):
        log.append((request.method, request.url.path, request.headers.get("x-gladia-key")))
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"audio_url": "https://api.gladia.io/file/abc"})
        if request.method == "POST" and request.url.path == "/v2/pre-recorded":
            log.append(("body", json.loads(request.content)))
            return httpx.Response(201, json={"id": "job1", "result_url": "https://api.gladia.io/v2/pre-recorded/job1"})
        if request.method == "GET":
            polls["n"] += 1
            if polls["n"] < 2:
                return httpx.Response(200, json={"status": "processing"})
            return httpx.Response(200, json={"status": "done", "result": {
                "metadata": {"audio_duration": 31.5},
                "transcription": {"full_transcript": "Waar komt u voor? Yeah, hoofdpijn.", "languages": ["nl"],
                                  "utterances": [
                                      {"text": "Waar komt u voor?", "start": 0, "end": 1.2, "speaker": 0, "confidence": 0.9},
                                      {"text": "Yeah, hoofdpijn.", "start": 1.5, "end": 3.0, "speaker": 1, "confidence": 0.8}]}}})
        if request.method == "DELETE":
            return httpx.Response(202)
        return httpx.Response(404)
    return handler


def test_gladia_job_speakers_and_cleanup(monkeypatch):
    log = []
    _mock(monkeypatch, _gladia(log))
    res = asyncio.run(stt_service.transcribe_eu(b"\x1aE\xdf\xa3" + b"0" * 2000, "nl", provider="gladia"))
    assert res.provider == "gladia" and res.duration_secs == 31.5
    assert [s.speaker for s in res.segments] == ["spreker_0", "spreker_1"]
    assert res.segments[1].text == "Ja, hoofdpijn."          # Dutch fillers, as with Voxtral
    assert "Spreker 1:" in stt_service.met_sprekers(res)
    body = next(x[1] for x in log if x[0] == "body")
    assert body["diarization"] is True and body["language_config"] == {"languages": ["nl"], "code_switching": False}
    assert body["custom_vocabulary"] is True and body["custom_vocabulary_config"]["vocabulary"]
    assert all(x[2] == "gladia-test" for x in log if x[0] != "body")
    assert ("DELETE", "/v2/pre-recorded/job1", "gladia-test") in log   # nothing stays behind


def test_gladia_detects_language_for_interpreter(monkeypatch):
    log = []
    _mock(monkeypatch, _gladia(log))
    asyncio.run(stt_service.transcribe_eu(b"0" * 2000, None, diarize=False, provider="gladia"))
    body = next(x[1] for x in log if x[0] == "body")
    assert body["diarization"] is False and body["language_config"] == {"languages": [], "code_switching": True}
    assert "custom_vocabulary" not in body       # Dutch words only help Dutch speech


SM_TRANSCRIPT = {
    "job": {"id": "j9", "duration": 12},
    "metadata": {"transcription_config": {"language": "tr"}},
    "results": [
        {"type": "word", "start_time": 0.1, "end_time": 0.4, "alternatives": [{"content": "Başım", "speaker": "S1", "confidence": 0.9}]},
        {"type": "word", "start_time": 0.5, "end_time": 0.9, "alternatives": [{"content": "ağrıyor", "speaker": "S1"}]},
        {"type": "punctuation", "start_time": 0.9, "end_time": 0.9, "attaches_to": "previous", "alternatives": [{"content": ".", "speaker": "S1"}]},
        {"type": "word", "start_time": 1.2, "end_time": 1.6, "alternatives": [{"content": "Sinds", "speaker": "S2"}]},
        {"type": "word", "start_time": 1.6, "end_time": 1.9, "alternatives": [{"content": "wanneer", "speaker": "S2"}]},
        {"type": "punctuation", "start_time": 1.9, "end_time": 1.9, "attaches_to": "previous", "alternatives": [{"content": "?", "speaker": "S2"}]},
    ],
}


def test_speechmatics_job_words_to_utterances_and_cleanup(monkeypatch):
    log = []
    polls = {"n": 0}

    def handler(request: httpx.Request):
        log.append((request.method, request.url.path, request.headers.get("authorization"), request.url.host))
        if request.method == "POST":
            log.append(("body", request.content.decode("utf-8", "replace")))
            return httpx.Response(201, json={"id": "j9"})
        if request.url.path == "/v2/jobs/j9":
            polls["n"] += 1
            if request.method == "DELETE":
                return httpx.Response(200, json={"job": {"status": "deleted"}})
            return httpx.Response(200, json={"job": {"status": "running" if polls["n"] < 2 else "done"}})
        if request.url.path == "/v2/jobs/j9/transcript":
            assert request.url.params["format"] == "json-v2"
            return httpx.Response(200, json=SM_TRANSCRIPT)
        return httpx.Response(404)

    _mock(monkeypatch, handler)
    res = asyncio.run(stt_service.transcribe_eu(b"0" * 2000, "tr", provider="speechmatics"))
    assert res.provider == "speechmatics" and res.duration_secs == 12 and res.language == "tr"
    assert [(s.speaker, s.text) for s in res.segments] == [("spreker_S1", "Başım ağrıyor."),
                                                           ("spreker_S2", "Sinds wanneer?")]
    body = next(x[1] for x in log if x[0] == "body")
    config = json.loads(body.split('name="config"')[1].split("\r\n\r\n", 1)[1].split("\r\n--")[0])
    tc = config["transcription_config"]
    assert tc["language"] == "tr" and tc["diarization"] == "speaker" and tc["operating_point"] == "enhanced"
    assert all(x[3] == "eu1.asr.api.speechmatics.com" and x[2] == "Bearer sm-test" for x in log if x[0] != "body")
    assert ("DELETE", "/v2/jobs/j9", "Bearer sm-test", "eu1.asr.api.speechmatics.com") in log


def test_speechmatics_rejected_job_is_an_error_and_still_deleted(monkeypatch):
    log = []

    def handler(request: httpx.Request):
        log.append(request.method)
        if request.method == "POST":
            return httpx.Response(201, json={"id": "j1"})
        if request.method == "GET":
            return httpx.Response(200, json={"job": {"status": "rejected"}})
        return httpx.Response(200)

    _mock(monkeypatch, handler)
    with pytest.raises(ValueError, match="Speechmatics"):
        asyncio.run(stt_service.transcribe_eu(b"0" * 2000, "nl", provider="speechmatics"))
    assert log[-1] == "DELETE"


def test_missing_keys_are_refused_before_sending(monkeypatch):
    monkeypatch.setenv("GLADIA_API_KEY", "")
    monkeypatch.setenv("SPEECHMATICS_API_KEY", "")
    get_config.cache_clear()
    for dienst in ("gladia", "speechmatics"):
        with pytest.raises(ValueError, match="niet geconfigureerd"):
            asyncio.run(stt_service.transcribe_eu(b"0", "nl", provider=dienst))


def test_policy_eu_stt_provider(monkeypatch):
    tok = data_policy.zet_modus("eu")
    try:
        assert data_policy.stt_provider() == "voxtral"
        monkeypatch.setenv("EU_STT_PROVIDER", "Gladia")
        assert data_policy.stt_provider() == "gladia" and data_policy.batch_stt()
        monkeypatch.setenv("EU_STT_PROVIDER", "deepgram")      # never a non-EU service in the eu mode
        assert data_policy.stt_provider() == "voxtral"
        monkeypatch.setenv("EU_STT_PROVIDER", "speechmatics")
        monkeypatch.setenv("SPEECHMATICS_API_KEY", "")
        get_config.cache_clear()
        assert "SPEECHMATICS_API_KEY" in (data_policy.eu_gereed() or "")
        assert data_policy.summary()["stt_eu_provider"] is True
    finally:
        data_policy.herstel_modus(tok)
    tok = data_policy.zet_modus("claude")
    try:
        assert data_policy.stt_provider() == "deepgram"        # the claude mode is unchanged
    finally:
        data_policy.herstel_modus(tok)


def test_interpreter_understands_all_languages_with_gladia(monkeypatch):
    tok = data_policy.zet_modus("eu")
    try:
        assert not tolk.verstaat(tolk.TALEN["tr"])                # Voxtral: no Turkish
        monkeypatch.setenv("EU_STT_PROVIDER", "gladia")
        assert all(tolk.verstaat(t) for t in tolk.TALEN.values())
        gezien = {}

        async def nep(audio, language=None, naam="", diarize=True, provider=None):
            gezien.update(language=language, provider=provider, diarize=diarize)
            return stt_service.TranscriptResult(raw_text="Başım ağrıyor", provider=provider)
        monkeypatch.setattr(stt_service, "transcribe_eu", nep)
        tekst = asyncio.run(tolk.spraak_naar_tekst(b"0", tolk.TALEN["ar-MA"], None))
        assert tekst == "Başım ağrıyor"
        assert gezien == {"language": "ar-MA", "provider": "gladia", "diarize": False}
    finally:
        data_policy.herstel_modus(tok)


def test_spraaktest_against_gladia(monkeypatch):
    gezien = []

    async def nep(pad, provider=None, deepgram_key=None, language=None):
        gezien.append(provider)
        return stt_service.TranscriptResult(raw_text="hoofdpijn paracetamol", duration_secs=60, provider=provider,
                                            segments=[stt_service.TranscriptSegment("hoofdpijn", 0, 1, "a")])
    monkeypatch.setattr(stt_service, "transcribe", nep)

    async def log(*a, **k):
        return None
    monkeypatch.setattr(register, "log", log)

    async def aan():
        return True
    monkeypatch.setattr(beheer, "testgereedschap_aan", aan)    # the switch in Beheer, on for this test
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test"
    try:
        api = TestClient(main.app)
        audio = {"audio": ("t.webm", b"0" * 2000, "audio/webm")}
        d = api.post("/api/v1/beheer/spraaktest", files=audio, data={"taal": "tr", "tegen": "gladia"}).json()
        assert sorted(gezien) == ["deepgram", "gladia"] and d["eu_dienst"] == "gladia"
        assert d["voxtral"]["aanbieder"] == "gladia" and d["voxtral"]["kosten_dollar"] is None   # price per contract
        monkeypatch.setenv("PRIJS_GLADIA_PER_MINUUT", "0,01")
        d = api.post("/api/v1/beheer/spraaktest", files=audio, data={"tegen": "gladia"}).json()
        assert d["voxtral"]["kosten_dollar"] == [0.01, 0.01]
        assert api.post("/api/v1/beheer/spraaktest", files=audio, data={"tegen": "deepgram"}).status_code == 400
        monkeypatch.setenv("SPEECHMATICS_API_KEY", "")
        get_config.cache_clear()
        r = api.post("/api/v1/beheer/spraaktest", files=audio, data={"tegen": "speechmatics"})
        assert r.status_code == 400 and "SPEECHMATICS_API_KEY" in r.json()["detail"]
    finally:
        main.app.dependency_overrides.clear()
