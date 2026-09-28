"""
Tests voor live dicteren (zijpaneel): Deepgram-relay en dictaatverwerking.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from services.cloud_api import dictation, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _results(text, is_final=True, speech_final=False):
    return json.dumps({
        "type": "Results",
        "is_final": is_final,
        "speech_final": speech_final,
        "channel": {"alternatives": [{"transcript": text}]},
    })


# === URL en berichtverwerking ===

def test_deepgram_url_has_low_latency_dutch_settings():
    params = parse_qs(urlparse(dictation.build_deepgram_url(get_config())).query)
    assert params["model"] == ["nova-3"]
    assert params["language"] == ["nl"]
    assert params["interim_results"] == ["true"]
    assert params["endpointing"] == ["300"]
    assert 0 < len(params["keyterm"]) <= dictation.MAX_KEYTERMS


def test_keyterms_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DICTATION_KEYTERMS", "false")
    get_config.cache_clear()
    params = parse_qs(urlparse(dictation.build_deepgram_url(get_config())).query)
    assert "keyterm" not in params


def test_keyterms_skipped_for_nova2(monkeypatch):
    monkeypatch.setenv("DICTATION_DEEPGRAM_MODEL", "nova-2")
    get_config.cache_clear()
    params = parse_qs(urlparse(dictation.build_deepgram_url(get_config())).query)
    assert "keyterm" not in params


def test_user_keyterms_come_first_and_are_capped():
    user = [f"term{i}" for i in range(80)]
    terms = dictation.build_keyterms(dictation.sanitize_user_keyterms(user))
    assert terms[:50] == user[:50]
    assert len(terms) <= dictation.MAX_KEYTERMS


def test_keyterms_stay_within_deepgram_token_budget():
    # Deepgram refuses the handshake above 500 keyterm tokens (HTTP 400).
    for user in ([], [f"lang medisch begrip nummer {i}" for i in range(50)]):
        terms = dictation.build_keyterms(dictation.sanitize_user_keyterms(user))
        used = sum(dictation.estimate_keyterm_tokens(t) for t in terms)
        assert used <= dictation.MAX_KEYTERM_TOKENS
        assert sum(len(t) for t in terms) < 1000


def test_relay_retries_with_fewer_keyterms_after_400():
    upstream = FakeUpstream([_results("hoofdpijn", speech_final=True)])
    seen = []
    app = FastAPI()

    async def picky_connect(url, api_key):
        seen.append(url)
        if len(seen) == 1:
            raise OSError("server rejected WebSocket connection: HTTP 400")
        return upstream

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket):
        await dictation.relay_dictation(ws, connect=picky_connect)

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "geheim"}))
        assert ws.receive_json() == {"type": "ready"}
        ws.send_text(json.dumps({"type": "stop"}))
        _receive_until_closed(ws)

    assert len(seen) == 2
    assert len(parse_qs(urlparse(seen[1]).query)["keyterm"]) < len(parse_qs(urlparse(seen[0]).query)["keyterm"])


def test_core_medical_terms_are_sent_before_other_drugs():
    terms = dictation.build_keyterms()
    assert terms[0] == "hypertensie"
    assert "atriumfibrilleren" in terms and "amoxicilline" in terms
    assert len(terms) <= dictation.MAX_KEYTERMS
    assert len({t.lower() for t in terms}) == len(terms)


@pytest.mark.parametrize("raw, expected", [
    (None, []),
    ("normaal longen", []),
    (["normaal  longen", "Normaal longen", "", 42, "x" * 51, "diclofenac"],
     ["normaal longen", "diclofenac"]),
])
def test_sanitize_user_keyterms(raw, expected):
    assert dictation.sanitize_user_keyterms(raw) == expected


def test_spoken_commands_become_line_breaks():
    text = "Keelpijn sinds drie dagen, nieuwe regel geen koorts. Nieuwe alinea plan paracetamol"
    assert dictation.apply_spoken_commands(text) == (
        "Keelpijn sinds drie dagen\ngeen koorts\n\nplan paracetamol"
    )


def test_parse_final_segment_is_corrected():
    event = dictation.parse_deepgram_message(_results("start met amoxicilline", speech_final=True))
    assert event == {
        "type": "transcript",
        "text": "start met amoxicilline",
        "is_final": True,
        "speech_final": True,
    }


def test_parse_interim_segment_passes_through():
    event = dictation.parse_deepgram_message(_results("nieuwe regel", is_final=False))
    # Interim tekst blijft rauw; commando's pas bij de definitieve versie.
    assert event["text"] == "nieuwe regel"
    assert event["is_final"] is False


@pytest.mark.parametrize("raw", [
    json.dumps({"type": "Metadata"}),
    _results("   "),
    "geen json",
])
def test_parse_ignores_irrelevant_messages(raw):
    assert dictation.parse_deepgram_message(raw) is None


# === WebSocket-relay met nagebootste Deepgram ===

class FakeUpstream:
    """Stands in for the Deepgram socket: records audio, replies on CloseStream."""

    def __init__(self, replies):
        self.replies = replies
        self.audio = []
        self.queue = asyncio.Queue()
        self.closed = False

    async def send(self, data):
        if isinstance(data, bytes):
            self.audio.append(data)
        elif json.loads(data).get("type") == "CloseStream":
            for reply in self.replies:
                await self.queue.put(reply)
            await self.queue.put(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self):
        self.closed = True


def _relay_app(upstream, seen_urls):
    app = FastAPI()

    async def fake_connect(url, api_key):
        seen_urls.append((url, api_key))
        return upstream

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket):
        await dictation.relay_dictation(ws, connect=fake_connect)

    return app


def _receive_until_closed(ws):
    events = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["type"] == "closed":
            return events


def test_relay_streams_audio_and_returns_transcript():
    upstream = FakeUpstream([
        _results("patiënt heeft", is_final=False),
        _results("patiënt heeft hoofdpijn", speech_final=True),
        json.dumps({"type": "Metadata"}),
    ])
    seen = []
    client = TestClient(_relay_app(upstream, seen))

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "geheim", "keyterms": ["normaal longen"]}))
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"chunk-1")
        ws.send_bytes(b"chunk-2")
        ws.send_text(json.dumps({"type": "stop"}))
        events = _receive_until_closed(ws)

    assert upstream.audio == [b"chunk-1", b"chunk-2"]
    assert upstream.closed
    assert seen[0][1] == "dg-test"
    assert parse_qs(urlparse(seen[0][0]).query)["keyterm"][0] == "normaal longen"
    transcripts = [e for e in events if e["type"] == "transcript"]
    assert [t["is_final"] for t in transcripts] == [False, True]
    assert transcripts[-1]["text"] == "patiënt heeft hoofdpijn"


def test_relay_rejects_wrong_api_key():
    seen = []
    client = TestClient(_relay_app(FakeUpstream([]), seen))

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "fout"}))
        event = ws.receive_json()

    assert event["type"] == "error"
    assert seen == []  # Deepgram nooit benaderd


def test_relay_reports_upstream_failure():
    app = FastAPI()

    async def failing_connect(url, api_key):
        raise OSError("HTTP 400")

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket):
        await dictation.relay_dictation(ws, connect=failing_connect)

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "geheim"}))
        event = ws.receive_json()

    assert event["type"] == "error"
    assert "HTTP 400" in event["message"]


# === Dictaat opschonen / SOEP ===

@pytest.fixture
def api():
    return TestClient(main.app)


def test_process_clean_returns_plain_text(api):
    with patch.object(main.llm_service, "complete", AsyncMock(return_value="  Hoofdpijn sinds 2d.  ")) as llm:
        resp = api.post(
            "/api/v1/dictation/process",
            json={"text": "eh hoofdpijn eh sinds 2d", "mode": "clean"},
            headers={"X-API-Key": "geheim"},
        )
    assert resp.status_code == 200
    assert resp.json()["text"] == "Hoofdpijn sinds 2d."
    assert llm.await_args.kwargs.get("json_mode", False) is False


def test_process_soep_returns_all_fields(api):
    soep = {"s": "3d keelpijn", "o": "", "e": "virale faryngitis", "p": "paracetamol",
            "icpc_code": "R74", "icpc_titel": None}
    with patch.object(main.llm_service, "complete", AsyncMock(return_value=json.dumps(soep))) as llm:
        resp = api.post(
            "/api/v1/dictation/process",
            json={"text": "keelpijn drie dagen", "mode": "soep", "llm_provider": "anthropic"},
            headers={"X-API-Key": "geheim"},
        )
    assert resp.status_code == 200
    body = resp.json()["soep"]
    assert body["s"] == "3d keelpijn"
    assert body["o"] == ""
    assert body["icpc_titel"] == ""
    assert llm.await_args.kwargs["json_mode"] is True
    # AVG: patient text goes to the EU model, whatever the browser asks for
    assert llm.await_args.kwargs["provider"] == "anthropic"
    assert body["aandachtspunten"] == []   # model gaf er geen: lege lijst


def test_process_soep_passes_attention_points_capped(api):
    soep = {"s": "2w hoesten, sinds gisteren koorts", "o": "", "e": "pneumonie",
            "p": "amoxicilline 3dd 500 mg 7d", "icpc_code": "R81", "icpc_titel": "Pneumonie",
            "aandachtspunten": ["Temperatuur?", " ", "Allergie voor penicilline?", "a", "b", "c"]}
    with patch.object(main.llm_service, "complete", AsyncMock(return_value=json.dumps(soep))) as llm:
        resp = api.post(
            "/api/v1/dictation/process",
            json={"text": "hoesten koorts amoxicilline", "mode": "soep"},
            headers={"X-API-Key": "geheim"},
        )
    body = resp.json()["soep"]
    assert body["aandachtspunten"] == ["Temperatuur?", "Allergie voor penicilline?", "a", "b"]
    schema = llm.await_args.kwargs["json_schema"]
    assert "aandachtspunten" in schema["required"]


def test_dictation_soep_prompt_forbids_inventing_but_asks_to_restructure():
    from services.cloud_api import prompts
    p = prompts.DICTAAT_SOEP_SYSTEM_PROMPT
    assert "NOOIT feiten toe" in p and "[?]" in p and "aandachtspunten" in p
    assert "VOLLEDIGHEID VAN DE VERSLAGLEGGING" in p   # no clinical advice (MDR)
    assert "aandachtspunten" not in prompts.SOEP_JSON_SCHEMA["properties"]


def test_process_soep_bad_json_is_502(api):
    with patch.object(main.llm_service, "complete", AsyncMock(return_value="geen json")):
        resp = api.post(
            "/api/v1/dictation/process",
            json={"text": "keelpijn", "mode": "soep"},
            headers={"X-API-Key": "geheim"},
        )
    assert resp.status_code == 502


def test_process_requires_api_key(api):
    resp = api.post("/api/v1/dictation/process", json={"text": "x", "mode": "clean"})
    assert resp.status_code == 401


def test_process_rejects_unknown_mode(api):
    resp = api.post(
        "/api/v1/dictation/process",
        json={"text": "x", "mode": "samenvatten"},
        headers={"X-API-Key": "geheim"},
    )
    assert resp.status_code == 422


# === Claude-modelroute: Haiku (prefill) vs Sonnet 5 (structured outputs) ===

def _fake_anthropic(content, stop_reason="end_turn"):
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"content": content, "stop_reason": stop_reason, "usage": {}})
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_soep_on_sonnet5_uses_structured_output_without_prefill(monkeypatch):
    from services.cloud_api import llm_service
    from services.cloud_api.prompts import SOEP_JSON_SCHEMA
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    get_config.cache_clear()
    client = _fake_anthropic([
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": '{"s": "keelpijn"}'},
    ])
    with patch.object(llm_service.httpx, "AsyncClient", return_value=client):
        out = await llm_service.complete(
            "sys", "usr", provider="anthropic", json_mode=True, max_tokens=900,
            quality=True, json_schema=SOEP_JSON_SCHEMA,
        )
    body = client.post.call_args.kwargs["json"]
    assert body["model"] == "claude-sonnet-5"
    assert "temperature" not in body
    assert body["messages"][-1]["role"] == "user"          # geen prefill
    assert body["output_config"]["format"]["schema"] == SOEP_JSON_SCHEMA
    assert body["max_tokens"] >= llm_service.MODERN_MIN_MAX_TOKENS
    assert json.loads(out) == {"s": "keelpijn"}            # tekstblok na thinking


@pytest.mark.asyncio
async def test_light_tasks_stay_on_haiku_with_prefill(monkeypatch):
    from services.cloud_api import llm_service
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    get_config.cache_clear()
    client = _fake_anthropic([{"type": "text", "text": '"decisief": "x"}'}])
    with patch.object(llm_service.httpx, "AsyncClient", return_value=client):
        out = await llm_service.complete("sys", "usr", provider="anthropic", json_mode=True, max_tokens=300)
    body = client.post.call_args.kwargs["json"]
    assert body["model"].startswith("claude-haiku-4-5")
    assert body["temperature"] == 0.1
    assert body["messages"][-1] == {"role": "assistant", "content": "{"}
    assert json.loads(out) == {"decisief": "x"}


@pytest.mark.asyncio
async def test_refusal_raises_clear_error(monkeypatch):
    from services.cloud_api import llm_service
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    get_config.cache_clear()
    client = _fake_anthropic([], stop_reason="refusal")
    with patch.object(llm_service.httpx, "AsyncClient", return_value=client):
        with pytest.raises(ValueError):
            await llm_service.complete("sys", "usr", provider="anthropic", quality=True)


# === Gegevensbeleid (AVG) ===

def test_policy_defaults(monkeypatch):
    from services.cloud_api import data_policy
    for k in ("PHI_LLM_PROVIDER", "LETTERS_LLM_PROVIDER", "ALLOWED_STT_PROVIDERS", "CLINICAL_DECISION_SUPPORT"):
        monkeypatch.delenv(k, raising=False)
    assert data_policy.phi_llm_provider("mistral") == "anthropic"
    assert data_policy.letters_llm_provider() == "anthropic"
    assert data_policy.stt_provider("openai") == "deepgram"
    assert data_policy.clinical_decision_support() is False


def test_deepgram_stream_opts_out_of_training():
    params = parse_qs(urlparse(dictation.build_deepgram_url(get_config())).query)
    assert params["mip_opt_out"] == ["true"]
    assert urlparse(dictation.build_deepgram_url(get_config())).hostname == "api.eu.deepgram.com"


@pytest.mark.parametrize("spoken,expected", [
    ("koorts komma hoesten punt", "koorts, hoesten."),
    ("temp 38 komma 5", "temp 38,5"),
    ("drukpijn McBurney punt rechts", "drukpijn McBurney punt rechts"),
    ("S dubbele punt hoofdpijn puntkomma misselijk", "S: hoofdpijn; misselijk"),
    ("wat is de klacht vraagteken", "wat is de klacht?"),
])
def test_spoken_punctuation(spoken, expected):
    assert dictation.apply_spoken_commands(spoken) == expected
