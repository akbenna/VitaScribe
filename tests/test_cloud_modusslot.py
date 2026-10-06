"""Praktijkslot op de modus (stuk 14, stap 3): wat niet mag, kan ook niet."""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from services.cloud_api import data_policy, dictation, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("MISTRAL_API_KEY", "m")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.delenv("TOEGESTANE_MODI", raising=False)
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


CLAUDE = {"X-API-Key": "geheim", "X-VitaScribe-Modus": "claude"}
EU = {"X-API-Key": "geheim", "X-VitaScribe-Modus": "eu"}


def test_standaard_beide_modi(api):
    assert api.get("/api/v1/providers", headers=CLAUDE).json()["modi"] == ["claude", "eu"]
    assert api.get("/api/v1/tolk/talen", headers=CLAUDE).status_code == 200


def test_alleen_eu_weigert_claude_met_uitleg(api, monkeypatch):
    monkeypatch.setenv("TOEGESTANE_MODI", "eu")
    r = api.get("/api/v1/tolk/talen", headers=CLAUDE)
    assert r.status_code == 403 and "alleen in de EU-modus" in r.json()["detail"]
    assert api.get("/api/v1/tolk/talen", headers=EU).status_code == 200
    # The extension can always ask which modes are allowed, also from the wrong mode.
    p = api.get("/api/v1/providers", headers=CLAUDE)
    assert p.status_code == 200 and p.json()["modi"] == ["eu"]
    # Without a mode header the default is claude: refused as well.
    assert api.get("/api/v1/tolk/talen", headers={"X-API-Key": "geheim"}).status_code == 403


def test_tikfout_opent_nooit_de_vs_route(monkeypatch):
    monkeypatch.setenv("TOEGESTANE_MODI", "ue")
    assert data_policy.server_modi() == ["eu"]
    monkeypatch.setenv("TOEGESTANE_MODI", "EU, claude")
    assert data_policy.server_modi() == ["claude", "eu"]


def test_praktijk_alleen_eu_vernauwt_de_server():
    assert data_policy.toegestane_modi(SimpleNamespace(alleen_eu=True)) == ["eu"]
    assert data_policy.toegestane_modi(SimpleNamespace(alleen_eu=False)) == ["claude", "eu"]


def test_websocket_dicteren_geweigerd_buiten_de_toegestane_modus(monkeypatch):
    monkeypatch.setenv("TOEGESTANE_MODI", "eu")
    gezien = []

    async def connect(url, api_key):
        gezien.append(url)
        raise AssertionError("mag Deepgram niet bereiken")
    app = FastAPI()

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket):
        await dictation.relay_dictation(ws, connect=connect)
    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "geheim", "modus": "claude"}))
        event = ws.receive_json()
    assert event["type"] == "error" and "EU-modus" in event.get("message", json.dumps(event))
    assert gezien == []
