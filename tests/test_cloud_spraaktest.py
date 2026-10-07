"""Voxtral (Mistral, EU) als spraakdienst, en de spraaktest tegen Deepgram."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from services.cloud_api import beheer, main, pipeline, register, spraaktest, stt_service
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    async def aan():
        return True
    monkeypatch.setattr(beheer, "testgereedschap_aan", aan)   # the admin switch in Beheer, off by default
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


VOXTRAL_ANTWOORD = {
    "model": "voxtral-mini-2602",
    "text": "Waar komt u voor? Ik heb al drie dagen hoofdpijn. Neemt u paracetamol?",
    "language": "nl",
    "usage": {"prompt_audio_seconds": 42},
    "segments": [
        {"text": "Waar komt u voor?", "start": 0.0, "end": 1.4, "speaker_id": "speaker_0", "type": "transcription_segment"},
        {"text": "Ik heb al drie dagen hoofdpijn.", "start": 1.6, "end": 3.9, "speaker_id": "speaker_1", "type": "transcription_segment"},
        {"text": "Neemt u paracetamol?", "start": 4.2, "end": 5.5, "speaker_id": "speaker_0", "type": "transcription_segment"},
    ],
}


def test_voxtral_request_and_speakers(monkeypatch, tmp_path):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content.decode("latin-1")
        return httpx.Response(200, json=VOXTRAL_ANTWOORD)

    echte = httpx.AsyncClient
    monkeypatch.setattr(stt_service.httpx, "AsyncClient",
                        lambda **kw: echte(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))
    audio = tmp_path / "consult.webm"
    audio.write_bytes(b"\x1aE\xdf\xa3" + b"0" * 2000)
    res = asyncio.run(stt_service.transcribe(audio, provider="voxtral", language="nl"))

    assert seen["url"] == "https://api.mistral.ai/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer mistral-test"
    body = seen["body"]
    assert 'name="diarize"' in body and "true" in body
    assert 'name="language"' in body and 'name="model"' in body and "voxtral-mini-latest" in body
    assert body.count('name="context_bias"') == len(stt_service.voxtral_context_bias()) <= 100
    assert res.provider == "voxtral" and res.duration_secs == 42
    assert [s.speaker for s in res.segments] == ["spreker_speaker_0", "spreker_speaker_1", "spreker_speaker_0"]
    # the language model gets the conversation per speaker, as with Deepgram
    assert stt_service.met_sprekers(res).splitlines() == [
        "Spreker 1: Waar komt u voor?", "Spreker 2: Ik heb al drie dagen hoofdpijn.", "Spreker 1: Neemt u paracetamol?"]


def test_voxtral_context_bias_has_no_spaces_or_commas():
    termen = stt_service.voxtral_context_bias()
    assert termen and all(" " not in t and "," not in t for t in termen)


def test_voxtral_error_is_readable_and_language_retry(monkeypatch, tmp_path):
    calls = []

    def handler(request: httpx.Request):
        body = request.content.decode("latin-1")
        calls.append('name="language"' in body)
        if 'name="language"' in body:
            return httpx.Response(400, json={"message": "language is not compatible with timestamp_granularities"})
        return httpx.Response(401, json={"message": "Unauthorized"})

    echte = httpx.AsyncClient
    monkeypatch.setattr(stt_service.httpx, "AsyncClient",
                        lambda **kw: echte(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"0" * 2000)
    with pytest.raises(ValueError, match="Voxtral gaf fout 401: Unauthorized"):
        asyncio.run(stt_service.transcribe(audio, provider="voxtral", language="nl"))
    assert calls == [True, False]


def test_voxtral_language_and_missing_key(monkeypatch, tmp_path):
    assert stt_service._voxtral_taal("multi") is None
    assert stt_service._voxtral_taal("en-GB") == "en"
    monkeypatch.delenv("MISTRAL_API_KEY")
    get_config.cache_clear()
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"0" * 2000)
    with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
        asyncio.run(stt_service.transcribe(audio, provider="voxtral"))


def test_overeenkomst_en_vaktermen():
    assert spraaktest.overeenkomst("Ik heb hoofdpijn", "ik heb hoofdpijn.") == 100.0
    assert spraaktest.overeenkomst("ik heb hoofdpijn", "ik had buikpijn") < 70
    assert "paracetamol" in [t.lower() for t in spraaktest.vaktermen("Neemt u Paracetamol?")]


def test_spraaktest_endpoint(monkeypatch):
    async def fake(pad, provider=None, language=None, **kw):
        if provider == "deepgram":
            return stt_service.TranscriptResult(
                raw_text="Waar komt u voor? Ik heb hoofdpijn. Neemt u paracetamol?", duration_secs=60, provider="deepgram",
                segments=[stt_service.TranscriptSegment("Waar komt u voor?", 0, 1, "spreker_0"),
                          stt_service.TranscriptSegment("Ik heb hoofdpijn.", 1, 2, "spreker_1")])
        raise httpx.ConnectError("geen verbinding")

    logs = []

    async def log(door, handeling, praktijk_id=None, **details):
        logs.append((door, handeling, details))

    monkeypatch.setattr(stt_service, "transcribe", fake)
    monkeypatch.setattr(register, "log", log)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test-beheerder"
    try:
        api = TestClient(main.app)
        r = api.post("/api/v1/beheer/spraaktest", files={"audio": ("rollenspel.webm", b"0" * 5000, "audio/webm")},
                     data={"taal": "nl"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["deepgram"]["sprekers"] == 2 and d["deepgram"]["kosten_dollar"] == [0.0048, 0.0077]
        assert "paracetamol" in [t.lower() for t in d["deepgram"]["vaktermen"]]
        # one provider failing does not fail the test page
        assert "fout" in d["voxtral"] and d["overeenkomst"] is None
        # the log holds no text
        assert logs and "hoofdpijn" not in json.dumps(logs)
        assert api.post("/api/v1/beheer/spraaktest", files={"audio": ("x.exe", b"0" * 5000)}).status_code == 400
        assert api.post("/api/v1/beheer/spraaktest", files={"audio": ("x.webm", b"0" * 10)}).status_code == 400
        assert api.get("/beheer/spraaktest").status_code == 200
    finally:
        main.app.dependency_overrides.clear()


def test_spraaktest_needs_admin():
    api = TestClient(main.app)
    r = api.post("/api/v1/beheer/spraaktest", files={"audio": ("x.webm", b"0" * 5000)})
    assert r.status_code in (401, 403, 503)


def test_spraaktest_soep(monkeypatch):
    gezien = []

    async def fake_soep(gesprek, aanbieder=None, taal=None):
        gezien.append((gesprek, aanbieder))
        if "Voxtral" in gesprek:
            raise ValueError("limiet bereikt")
        return pipeline.SOEPResult(s="Schouderklachten links.", e="Schouderklachten", icpc_code="L08",
                                   problemen=[{"s": "Schouderklachten links.", "o": "", "e": "Schouderklachten",
                                               "p": "", "icpc_code": "L08", "icpc_titel": "Schouderklachten"}])

    logs = []

    async def log(door, handeling, praktijk_id=None, **details):
        logs.append((door, handeling, details))

    monkeypatch.setattr(pipeline, "genereer_soep", fake_soep)
    monkeypatch.setattr(register, "log", log)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "test-beheerder"
    try:
        api = TestClient(main.app)
        r = api.post("/api/v1/beheer/spraaktest/soep",
                     json={"deepgram": "Spreker 1: Wat brengt u hier?\nSpreker 2: Pijn in mijn schouder.",
                           "voxtral": "Spreker 1: Voxtral tekst", "taal": "nl"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["deepgram"]["problemen"][0]["icpc_code"] == "L08"
        assert "limiet" in d["voxtral"]["fout"]
        # the production model for patient data, for both sides
        assert {a for _, a in gezien} == {d["taalmodel"]}
        assert logs and "schouder" not in json.dumps(logs).lower()
        assert api.post("/api/v1/beheer/spraaktest/soep", json={"deepgram": " ", "voxtral": ""}).status_code == 400
    finally:
        main.app.dependency_overrides.clear()


def test_spraaktest_soep_needs_admin():
    r = TestClient(main.app).post("/api/v1/beheer/spraaktest/soep", json={"deepgram": "x", "voxtral": "y"})
    assert r.status_code in (401, 403, 503)


def test_spraaktest_page_allows_only_cookieless_youtube_frame():
    api = TestClient(main.app)
    csp = api.get("/beheer/spraaktest").headers["content-security-policy"]
    assert "frame-src https://www.youtube-nocookie.com" in csp
    assert "script-src" not in csp and "default-src 'self'" in csp   # no YouTube script in the page
    # the other admin pages keep the strict policy
    assert "frame-src" not in api.get("/beheer").headers["content-security-policy"]


def test_voxtral_english_fillers_become_dutch():
    assert stt_service.nederlandse_vulwoorden("Yeah. Okay, goed. yep") == "Ja. Oké, goed. ja"
    assert stt_service.nederlandse_vulwoorden("Okayish blijft") == "Okayish blijft"


def test_voxtral_from_memory_and_fillers(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = request.content
        return httpx.Response(200, json={"text": "Yeah. Keelpijn.", "language": "nl", "usage": {"prompt_audio_seconds": 3},
                                         "segments": [{"text": "Yeah.", "start": 0, "end": 1, "speaker_id": "speaker_0"},
                                                      {"text": "Keelpijn.", "start": 1, "end": 2, "speaker_id": "speaker_1"}]})

    echte = httpx.AsyncClient
    monkeypatch.setattr(stt_service.httpx, "AsyncClient",
                        lambda **kw: echte(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))
    res = asyncio.run(stt_service.transcribe_bytes(b"OPNAME-IN-GEHEUGEN", "voxtral", language="nl"))
    assert b"OPNAME-IN-GEHEUGEN" in seen["body"] and b'filename="consult.webm"' in seen["body"]
    assert res.segments[0].text == "Ja." and res.raw_text == "Ja. Keelpijn."
    with pytest.raises(ValueError):
        asyncio.run(stt_service.transcribe_bytes(b"x", "deepgram"))
