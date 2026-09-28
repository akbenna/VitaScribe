"""
Tests: vraagsuggesties tijdens het live consult (klinische ondersteuning).
Alleen als de server het toestaat én de arts het aanzette; hooguit eens per
halve minuut; nooit na "Nadicteren"; een mislukte ronde hindert niets.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import consult_live, vraagsuggesties
from services.cloud_api.config import get_config
from services.cloud_api.consult_live import Gesprek
from tests.test_cloud_consult_live import AUTH, FakeUpstream, _app, _final, _tot_gesloten


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.delenv("CLINICAL_DECISION_SUPPORT", raising=False)
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _gesprek(woorden, nadictaat=False):
    g = Gesprek()
    g.verwerk(_final(*[(0, "woord", i * 0.3, i * 0.3 + 0.2) for i in range(woorden)]))
    if nadictaat:
        g.start_nadictaat(1.0)
    return g


def test_alleen_met_server_en_arts(monkeypatch):
    assert not vraagsuggesties.toegestaan({"vraagsuggesties": True})          # server uit
    monkeypatch.setenv("CLINICAL_DECISION_SUPPORT", "true")
    assert vraagsuggesties.toegestaan({"vraagsuggesties": True})
    assert not vraagsuggesties.toegestaan({})                                  # arts uit
    assert not vraagsuggesties.toegestaan({"vraagsuggesties": "ja"})


def test_schoon_houdt_het_kort_en_zonder_dubbelen():
    uit = vraagsuggesties.schoon({"klacht": "keelpijn", "vragen": [
        {"tekst": "koorts?", "alarm": False}, {"tekst": "Koorts?", "alarm": True},
        "slikklachten?", {"tekst": ""}, {"tekst": "stridor?", "alarm": True},
        {"tekst": "hoesten?"}, {"tekst": "reizen?"}]})
    assert [v["tekst"] for v in uit["vragen"]] == ["koorts?", "slikklachten?", "stridor?", "hoesten?"]
    assert uit["vragen"][2]["alarm"] is True


@pytest.mark.asyncio
async def test_meedenker_wacht_op_klacht_en_houdt_rust():
    nu = [0.0]
    gezonden = []
    maak = AsyncMock(return_value={"klacht": "keelpijn", "vragen": [{"tekst": "koorts?", "alarm": False}]})

    async def zend(p):
        gezonden.append(p)

    m = vraagsuggesties.Meedenker(zend, "dr", maak=maak, klok=lambda: nu[0])
    m.misschien(_gesprek(10))                  # begroeting: te weinig
    assert maak.await_count == 0
    m.misschien(_gesprek(30))
    await m.taak
    assert gezonden == [{"type": "suggesties", "klacht": "keelpijn", "vragen": [{"tekst": "koorts?", "alarm": False}]}]
    nu[0] = 10.0
    m.misschien(_gesprek(80))                  # binnen 30 s: geen nieuwe ronde
    assert maak.await_count == 1
    nu[0] = 40.0
    m.misschien(_gesprek(80))
    await m.taak
    assert maak.await_count == 2
    assert len(gezonden) == 1                  # zelfde uitkomst: niets opnieuw sturen


@pytest.mark.asyncio
async def test_meedenker_zwijgt_na_nadicteren_en_bij_fouten():
    gezonden = []

    async def zend(p):
        gezonden.append(p)

    m = vraagsuggesties.Meedenker(zend, maak=AsyncMock(side_effect=ValueError("stuk")))
    m.misschien(_gesprek(40, nadictaat=True))
    assert m.taak is None
    m.misschien(_gesprek(40))
    await m.taak                               # de fout wordt opgevangen
    assert gezonden == []


def test_prompt_geeft_alleen_vragen():
    p = vraagsuggesties.SYSTEM_PROMPT
    assert "geen diagnoses" in p and "NOG NIET gesteld" in p and "hooguit 4" in p


class PratendeUpstream(FakeUpstream):
    """Deepgram die al tijdens het consult tekst stuurt (bij het eerste geluid)."""

    def __init__(self, tijdens, na):
        super().__init__(na)
        self.tijdens = tijdens

    async def send(self, data):
        if isinstance(data, bytes) and self.tijdens:
            for r in self.tijdens:
                await self.queue.put(r)
            self.tijdens = []
        await super().send(data)


def _praat(n):
    return _final(*[(1, "keelpijn", i * 0.3, i * 0.3 + 0.2) for i in range(n)])


def test_live_consult_stuurt_suggesties_als_alles_aanstaat(monkeypatch):
    monkeypatch.setenv("CLINICAL_DECISION_SUPPORT", "true")
    uit = {"klacht": "keelpijn", "vragen": [{"tekst": "koorts?", "alarm": False}]}
    with patch.object(vraagsuggesties, "maak_suggesties", AsyncMock(return_value=uit)):
        client = TestClient(_app(PratendeUpstream([_praat(30)], []), [], []))
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps(dict(AUTH, vraagsuggesties=True)))
            assert ws.receive_json() == {"type": "ready"}
            ws.send_bytes(b"geluid")
            events = []
            while True:
                e = ws.receive_json()
                events.append(e)
                if e["type"] == "suggesties":
                    break
            ws.send_text(json.dumps({"type": "stop"}))
            events += _tot_gesloten(ws)
    sugg = [e for e in events if e["type"] == "suggesties"]
    assert sugg == [{"type": "suggesties", **uit}]


def test_live_consult_zonder_instelling_geen_suggesties(monkeypatch):
    maak = AsyncMock(return_value={"klacht": "x", "vragen": []})
    with patch.object(vraagsuggesties, "maak_suggesties", maak):
        client = TestClient(_app(PratendeUpstream([_praat(30)], []), [], []))
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps(dict(AUTH, vraagsuggesties=True)))   # arts wil, server niet
            assert ws.receive_json() == {"type": "ready"}
            ws.send_bytes(b"geluid")
            assert ws.receive_json()["type"] == "voortgang"
            ws.send_text(json.dumps({"type": "stop"}))
            events = _tot_gesloten(ws)
    assert maak.await_count == 0
    assert all(e["type"] != "suggesties" for e in events)
