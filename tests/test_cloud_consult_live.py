"""
Tests voor het live consult: het gesprek wordt gevolgd, na stop komt het verslag.
"""

import asyncio
import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from services.cloud_api import consult_live
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _final(*woorden):
    """Een Deepgram-final met woorden als (spreker, woord, begin, eind)."""
    return json.dumps({
        "type": "Results", "is_final": True,
        "channel": {"alternatives": [{
            "transcript": " ".join(w for _, w, _, _ in woorden),
            "words": [{"word": w.lower(), "punctuated_word": w, "speaker": s, "start": b, "end": e}
                      for s, w, b, e in woorden],
        }]},
    })


class FakeUpstream:
    """Staat in voor Deepgram: bewaart audio, antwoordt op CloseStream."""

    def __init__(self, replies, valt_weg=False):
        self.replies = replies
        self.audio = []
        self.queue = asyncio.Queue()
        self.closed = False
        if valt_weg:
            self.queue.put_nowait(None)

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


class FakeResult:
    def __init__(self, transcript):
        self.transcript = transcript

    def to_dict(self):
        return {"soep": {"s": "keelpijn"}, "transcript_raw": self.transcript.raw_text}


verwerkt_taal = []   # de taal die de live verwerking meekreeg


def _app(upstream, gezien, verwerkt):
    app = FastAPI()

    async def fake_connect(url, api_key):
        gezien.append((url, api_key))
        return upstream

    async def fake_verwerk(transcript, llm_provider=None, taal=None):
        verwerkt.append(transcript)
        verwerkt_taal.append(taal)
        return FakeResult(transcript)

    @app.websocket("/ws")
    async def route(ws: WebSocket):
        await consult_live.volg_consult(ws, connect=fake_connect, verwerk=fake_verwerk)

    return app


def _tot_gesloten(ws):
    events = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["type"] == "closed":
            return events


AUTH = {"type": "auth", "api_key": "geheim", "consent": True}


# === Adres en opbouw van het gesprek ===

def test_consult_url_scheidt_stemmen_zonder_tussentekst():
    q = parse_qs(urlparse(consult_live.build_consult_url(get_config())).query)
    assert q["diarize"] == ["true"]
    assert q["interim_results"] == ["false"]
    assert q["mip_opt_out"] == ["true"]
    assert q["model"] == ["nova-3"]
    assert q["language"] == ["nl"]
    assert "keyterm" in q
    assert urlparse(consult_live.build_consult_url(get_config())).netloc == "api.eu.deepgram.com"


def test_gesprek_bundelt_woorden_per_spreker_over_berichten_heen():
    g = consult_live.Gesprek()
    assert g.verwerk(_final((0, "Wat", 0.0, 0.2), (0, "is", 0.2, 0.3), (0, "er?", 0.3, 0.5)))
    assert g.verwerk(_final((1, "Keelpijn,", 1.0, 1.4), (1, "drie", 1.4, 1.6), (1, "dagen.", 1.6, 2.0)))
    assert g.verwerk(_final((1, "En", 2.1, 2.2), (1, "koorts.", 2.2, 2.6), (0, "Ik", 3.0, 3.1), (0, "kijk.", 3.1, 3.4)))
    t = g.transcript()
    assert [(s.speaker, s.text) for s in t.segments] == [
        ("spreker_0", "Wat is er?"),
        ("spreker_1", "Keelpijn, drie dagen. En koorts."),
        ("spreker_0", "Ik kijk."),
    ]
    assert t.duration_secs == 3.4
    assert t.provider == "deepgram-live"
    assert len(g.sprekers) == 2


def test_gesprek_negeert_tussentekst_en_ruis():
    g = consult_live.Gesprek()
    tussen = json.loads(_final((0, "Wat", 0.0, 0.2)))
    tussen["is_final"] = False
    assert not g.verwerk(json.dumps(tussen))
    assert not g.verwerk("geen json")
    assert not g.verwerk(b"binair")
    assert not g.verwerk(json.dumps({"type": "Metadata", "duration": 61.5}))
    assert g.seconden == 61.5
    assert g.transcript().raw_text == ""


# === Het hele consult over de WebSocket ===

def test_live_consult_levert_na_stop_het_verslag():
    upstream = FakeUpstream([
        _final((0, "Wat", 0.0, 0.2), (0, "kan", 0.2, 0.3), (0, "ik", 0.3, 0.4), (0, "doen?", 0.4, 0.6)),
        _final((1, "Keelpijn.", 1.0, 1.5)),
        json.dumps({"type": "Metadata", "duration": 2.0}),
    ])
    gezien, verwerkt = [], []
    client = TestClient(_app(upstream, gezien, verwerkt))

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(dict(AUTH, keyterms=["Lachman"])))
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"stuk-1")
        ws.send_bytes(b"stuk-2")
        ws.send_text(json.dumps({"type": "stop"}))
        events = _tot_gesloten(ws)

    assert upstream.audio == [b"stuk-1", b"stuk-2"]
    assert upstream.closed
    assert gezien[0][1] == "dg-test"
    assert parse_qs(urlparse(gezien[0][0]).query)["keyterm"][0] == "Lachman"

    soorten = [e["type"] for e in events]
    assert soorten == ["voortgang", "voortgang", "verwerken", "result", "closed"]
    assert events[1]["sprekers"] == 2
    result = events[3]
    assert result["leeg"] is False
    assert result["data"]["soep"] == {"s": "keelpijn"}
    assert "processing_time_secs" in result["data"]

    [transcript] = verwerkt
    assert [s.speaker for s in transcript.segments] == ["spreker_0", "spreker_1"]
    assert transcript.raw_text == "Wat kan ik doen? Keelpijn."


def test_live_consult_zonder_spraak_meldt_leeg():
    client = TestClient(_app(FakeUpstream([]), [], []))
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(AUTH))
        assert ws.receive_json() == {"type": "ready"}
        ws.send_text(json.dumps({"type": "stop"}))
        events = _tot_gesloten(ws)
    result = [e for e in events if e["type"] == "result"][0]
    assert result["leeg"] is True


def test_live_consult_zonder_toestemming_start_niet():
    gezien = []
    client = TestClient(_app(FakeUpstream([]), gezien, []))
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "geheim"}))
        event = ws.receive_json()
    assert event["type"] == "error"
    assert event["terugval"] is False
    assert "Toestemming" in event["message"]
    assert gezien == []   # Deepgram nooit benaderd


def test_live_consult_met_verkeerde_sleutel():
    gezien = []
    client = TestClient(_app(FakeUpstream([]), gezien, []))
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "auth", "api_key": "fout", "consent": True}))
        event = ws.receive_json()
    assert event["type"] == "error"
    assert event["terugval"] is False
    assert gezien == []


def test_wegvallende_spraakherkenning_vraagt_om_terugval():
    verwerkt = []
    client = TestClient(_app(FakeUpstream([], valt_weg=True), [], verwerkt))
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(AUTH))
        assert ws.receive_json() == {"type": "ready"}
        events = _tot_gesloten(ws)
    fout = [e for e in events if e["type"] == "error"][0]
    assert fout["terugval"] is True
    assert verwerkt == []


def test_onbereikbare_spraakherkenning_vraagt_om_terugval():
    app = FastAPI()

    async def kapot(url, api_key):
        raise OSError("netwerk")

    @app.websocket("/ws")
    async def route(ws: WebSocket):
        await consult_live.volg_consult(ws, connect=kapot)

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(AUTH))
        event = ws.receive_json()
    assert event["type"] == "error"
    assert event["terugval"] is True


def test_route_staat_in_de_app():
    from services.cloud_api import main
    assert any(getattr(r, "path", "") == "/api/v1/consult/stream" for r in main.app.routes)


# === Nadictaat ===

def test_gesprek_zet_woorden_na_de_klik_in_het_nadictaat():
    g = consult_live.Gesprek()
    g.verwerk(_final((0, "Wat", 0.0, 0.2), (1, "Keelpijn.", 1.0, 1.4)))
    g.start_nadictaat(10.0)
    g.verwerk(_final((0, "Keel", 12.0, 12.3), (0, "rood.", 12.3, 12.6)))
    t = g.transcript()
    assert [(s.speaker, s.text) for s in t.segments][-1] == ("nadictaat", "Keel rood.")
    assert len(g.sprekers) == 2   # het nadictaat telt niet als extra stem


def test_gesprek_negeert_een_onzinnige_nadictaattijd():
    g = consult_live.Gesprek()
    g.start_nadictaat("abc")
    g.start_nadictaat(-3)
    assert g.nadictaat_vanaf is None


def test_live_consult_met_nadictaat():
    upstream = FakeUpstream([
        _final((0, "Wat", 0.0, 0.2), (1, "Keelpijn.", 1.0, 1.4)),
        _final((0, "Keel", 12.0, 12.3), (0, "rood.", 12.3, 12.6)),
    ])
    verwerkt = []
    client = TestClient(_app(upstream, [], verwerkt))
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(AUTH))
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"stuk")
        ws.send_text(json.dumps({"type": "nadictaat", "vanaf": 10.0}))
        ws.send_text(json.dumps({"type": "stop"}))
        _tot_gesloten(ws)
    [transcript] = verwerkt
    assert transcript.segments[-1].speaker == "nadictaat"
    from services.cloud_api import stt_service
    assert stt_service.met_sprekers(transcript).endswith("Nadictaat arts: Keel rood.")


# === Taal van het consult ===

def test_taal_gaat_naar_deepgram_en_de_verwerking():
    from services.cloud_api import talen
    upstream = FakeUpstream([_final((0, "Merhaba", 0.0, 0.5))])
    gezien, verwerkt = [], []
    verwerkt_taal.clear()
    client = TestClient(_app(upstream, gezien, verwerkt))
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(dict(AUTH, taal="tr", keyterms=["Lachman"])))
        assert ws.receive_json() == {"type": "ready"}
        ws.send_text(json.dumps({"type": "stop"}))
        _tot_gesloten(ws)
    query = parse_qs(urlparse(gezien[0][0]).query)
    assert query["language"] == ["tr"]
    assert "keyterm" not in query            # Nederlandse keyterms niet bij Turks
    assert verwerkt_taal == ["tr"]
    assert talen.kies("xx").code == "nl" and talen.kies(None).code == "nl"


def test_meertalig_houdt_keyterms_en_standaard_is_nederlands():
    cfg = get_config()
    from services.cloud_api import talen
    multi = parse_qs(urlparse(consult_live.build_consult_url(cfg, ["Lachman"], taal=talen.kies("multi"))).query)
    assert multi["language"] == ["multi"] and "Lachman" in multi["keyterm"]
    standaard = parse_qs(urlparse(consult_live.build_consult_url(cfg)).query)
    assert standaard["language"] == ["nl"]


def test_prompt_vraagt_nederlandse_soep_bij_andere_taal():
    from services.cloud_api import talen
    assert talen.prompt_regel(talen.kies("nl")) == ""
    regel = talen.prompt_regel(talen.kies("pl"))
    assert "Pools" in regel and "Nederlands" in regel and "tolk" in regel
