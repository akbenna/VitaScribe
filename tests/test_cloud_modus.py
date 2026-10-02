"""Two modes: "claude" (all features) and "eu" (formal: only EU companies)."""

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from types import SimpleNamespace

from services.cloud_api import consult_live, data_policy, dictation, llm_service, main, stt_service
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    for naam in ("PHI_LLM_PROVIDER", "LETTERS_LLM_PROVIDER", "ALLOWED_STT_PROVIDERS", "EU_LLM_PROVIDER"):
        monkeypatch.delenv(naam, raising=False)
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_modes_choose_providers():
    t = data_policy.zet_modus("eu")
    try:
        assert data_policy.modus() == "eu"
        assert data_policy.phi_llm_provider("anthropic") == "mistral"   # the browser cannot pull it back
        assert data_policy.letters_llm_provider() == "mistral"
        assert data_policy.stt_provider("deepgram") == "voxtral"
        assert data_policy.summary()["patient_data_llm_in_eu"] is True
    finally:
        data_policy.herstel_modus(t)
    t = data_policy.zet_modus("claude")
    try:
        assert data_policy.phi_llm_provider() == "anthropic"
        assert data_policy.stt_provider() == "deepgram"
    finally:
        data_policy.herstel_modus(t)


def test_the_doctor_decides_never_the_server(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODI", "claude")      # an old setting has no effect
    assert data_policy.kies_modus("eu") == "eu"
    assert data_policy.kies_modus("claude") == "claude"
    assert data_policy.kies_modus(None) == "claude" and data_policy.kies_modus("onzin") == "claude"
    monkeypatch.setenv("EU_LLM_PROVIDER", "anthropic")      # not an EU provider: fail to Mistral
    assert data_policy.eu_llm_provider() == "mistral"
    monkeypatch.setenv("EU_LLM_PROVIDER", "bedrock")
    assert data_policy.eu_llm_provider() == "bedrock"


def test_eu_without_key_fails_and_never_falls_back_to_claude(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY")
    get_config.cache_clear()
    gezien = []

    async def fake_anthropic(*a, **kw):
        gezien.append("anthropic")
        return "{}"
    monkeypatch.setattr(llm_service, "_complete_anthropic", fake_anthropic)
    api = TestClient(main.app)
    r = api.get("/api/v1/providers", headers={"X-API-Key": "geheim", "X-VitaScribe-Modus": "eu"})
    assert r.json()["modus"] == "eu" and "Mistral-sleutel" in r.json()["eu_probleem"]
    r = api.post("/api/v1/dictation/process", headers={"X-API-Key": "geheim", "X-VitaScribe-Modus": "eu"},
                 json={"text": "keelpijn", "mode": "clean"})
    assert r.status_code >= 400 and gezien == []


def test_header_sets_mode_per_request():
    api = TestClient(main.app)
    r = api.get("/api/v1/providers", headers={"X-API-Key": "geheim", "X-VitaScribe-Modus": "eu"})
    assert r.status_code == 200
    assert r.json()["modus"] == "eu" and r.json()["modi"] == ["claude", "eu"] and r.json()["eu_probleem"] is None
    assert r.headers["x-vitascribe-modus"] == "eu"
    r = api.get("/api/v1/providers", headers={"X-API-Key": "geheim"})
    assert r.json()["modus"] == "claude" and r.headers["x-vitascribe-modus"] == "claude"
    # the mode does not leak into the next request
    assert data_policy.modus() == "claude"


def test_dictation_soep_uses_mistral_in_eu_mode(monkeypatch):
    gezien = []

    async def fake_complete(system_prompt, user_prompt, provider=None, **kw):
        gezien.append(provider)
        return json.dumps({"s": "keelpijn", "o": "", "e": "", "p": "", "icpc_code": "", "icpc_titel": ""})
    monkeypatch.setattr(llm_service, "complete", fake_complete)
    api = TestClient(main.app)
    for modus in ("eu", "claude"):
        r = api.post("/api/v1/dictation/process", headers={"X-API-Key": "geheim", "X-VitaScribe-Modus": modus},
                     json={"text": "keelpijn sinds drie dagen", "mode": "soep", "llm_provider": "anthropic"})
        assert r.status_code == 200, r.text
    assert gezien == ["mistral", "anthropic"]


def test_live_dictation_refused_in_eu_mode():
    app = FastAPI()

    async def nooit(url, key):
        raise AssertionError("geen Deepgram in de EU-modus")

    @app.websocket("/ws")
    async def route(ws: WebSocket):
        await dictation.relay_dictation(ws, connect=nooit)

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "geheim", "modus": "eu"}))
        e = ws.receive_json()
    assert e["type"] == "error" and "EU-modus" in e["message"]


def test_live_consult_follows_mode_from_auth():
    app = FastAPI()
    ontvangen = []

    async def nooit(url, key):
        raise AssertionError("geen Deepgram in de EU-modus")

    async def transcribeer(audio, provider, language=None):
        ontvangen.append(provider)
        return stt_service.TranscriptResult(raw_text="Keelpijn.", provider="voxtral", duration_secs=2,
                                            segments=[stt_service.TranscriptSegment("Keelpijn.", 0, 1, "spreker_speaker_1")])

    async def verwerk(transcript, llm_provider=None, taal=None):
        ontvangen.append(data_policy.phi_llm_provider())
        return SimpleNamespace(to_dict=lambda: {"soep": {}})

    @app.websocket("/ws")
    async def route(ws: WebSocket):
        await consult_live.volg_consult(ws, connect=nooit, verwerk=verwerk, transcribeer=transcribeer)

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "geheim", "consent": True, "modus": "eu"}))
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"opname")
        ws.send_text(json.dumps({"type": "stop"}))
        while ws.receive_json()["type"] != "closed":
            pass
    assert ontvangen == ["voxtral", "mistral"]


def test_letters_ignore_own_us_key_in_eu_mode(monkeypatch):
    from services.cloud_api import praktijk_sleutels

    async def eigen(praktijk_id, dienst):
        return ("anthropic", "eigen-sleutel")
    monkeypatch.setattr(praktijk_sleutels, "_eigen", eigen)
    ident = SimpleNamespace(brieven_in_eu=False, bron="register", praktijk_id="p1", eigen_sleutels_verplicht=False)
    t = data_policy.zet_modus("eu")
    try:
        assert asyncio.run(praktijk_sleutels.kies_brieven(ident)) == ("mistral", None)
    finally:
        data_policy.herstel_modus(t)
    assert asyncio.run(praktijk_sleutels.kies_brieven(ident)) == ("anthropic", "eigen-sleutel")


def test_mistral_gets_the_schema_as_instruction(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"s\": \"x\"}"}}]})

    echte = httpx.AsyncClient
    monkeypatch.setattr(llm_service.httpx, "AsyncClient",
                        lambda **kw: echte(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))
    schema = {"type": "object", "properties": {"s": {"type": "string"}}, "required": ["s"]}
    out = asyncio.run(llm_service.complete("sys", "vraag", provider="mistral", json_mode=True, json_schema=schema))
    assert out == "{\"s\": \"x\"}"
    body = seen["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][1]["content"].startswith("vraag") and '"required": ["s"]' in body["messages"][1]["content"]
