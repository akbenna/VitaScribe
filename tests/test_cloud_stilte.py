"""Stiltes inkorten voor de spraakherkenning (EU-modus): minder betaalde minuten,
zonder dat er spraak verdwijnt of het consult kan mislukken."""

import asyncio
import json
import shutil
import subprocess

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from services.cloud_api import beheer, consult_live, main, register, spraaktest, stilte, stt_service
from services.cloud_api.config import get_config

MET_FFMPEG = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ontbreekt")

LOG = """
[silencedetect @ 0x1] silence_start: 3.007
[silencedetect @ 0x1] silence_end: 9.004 | silence_duration: 5.997
[silencedetect @ 0x1] silence_start: 10.5
[silencedetect @ 0x1] silence_end: 11.2 | silence_duration: 0.7
[silencedetect @ 0x1] silence_start: 14.0
size=N/A time=00:00:18.00 bitrate=N/A speed= 300x
"""


def test_leest_stiltes_en_duur_uit_ffmpeg():
    stiltes, duur = stilte.lees_stiltes(LOG)
    assert duur == 18.0
    # a silence that runs to the end of the recording ends there
    assert stiltes == [(3.007, 9.004), (10.5, 11.2), (14.0, 18.0)]


def test_knipt_alleen_lange_stiltes_en_laat_een_randje_staan():
    knippen = stilte.knipplan([(3.0, 9.0), (10.5, 11.2), (14.0, 18.0)])
    # 0.7 s is a normal pause in a sentence: left alone
    assert knippen == [(3.0 + stilte.BEWAAR, 9.0 - stilte.BEWAAR), (14.0 + stilte.BEWAAR, 18.0 - stilte.BEWAAR)]


def test_verschuift_het_nadictaat_naar_de_ingekorte_opname():
    k = stilte.Ingekort(audio=b"", voor=60.0, na=40.0, knippen=[(10.0, 20.0), (30.0, 40.0)])
    assert k.verschuif(None) is None
    assert k.verschuif(5.0) == 5.0           # before any cut
    assert k.verschuif(15.0) == 10.0         # inside a cut: where the cut is
    assert k.verschuif(50.0) == 30.0         # after both cuts: 20 s earlier


def _toon(s, d, f=300):
    return f"sine=f={f}:d={d}"


def _opname(tmp_path, delen) -> bytes:
    """Tones (stand-in for speech) and digital silence, as webm/opus like the extension."""
    args, labels = [], []
    for i, (soort, d) in enumerate(delen):
        bron = f"sine=f={300 + 100 * i}:d={d}" if soort == "toon" else f"anullsrc=r=48000:cl=mono:d={d}"
        args += ["-f", "lavfi", "-i", bron]
        labels.append(f"[{i}]")
    pad = tmp_path / "opname.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args, "-filter_complex",
                    "".join(labels) + f"concat=n={len(delen)}:v=0:a=1", "-c:a", "libopus", "-b:a", "32k", str(pad)],
                   check=True)
    return pad.read_bytes()


def _duur(data: bytes, tmp_path) -> float:
    pad = tmp_path / "uit.ogg"
    pad.write_bytes(data)
    uit = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(pad)],
                         capture_output=True, text=True, check=True).stdout
    return float(uit)


@MET_FFMPEG
def test_kort_een_echte_opname_in_en_de_duur_klopt(tmp_path):
    audio = _opname(tmp_path, [("toon", 3), ("stil", 6), ("toon", 3), ("stil", 1), ("toon", 2)])
    k = asyncio.run(stilte.kort_in(audio))
    assert k is not None and k.naam.endswith(".ogg")
    assert len(k.knippen) == 1                     # the 1 s pause stays
    assert k.voor == pytest.approx(15.0, abs=0.2)
    assert k.na == pytest.approx(15.0 - 6.0 + 2 * stilte.BEWAAR, abs=0.2)
    # the container says the new length (a service that reads the header bills that)
    assert _duur(k.audio, tmp_path) == pytest.approx(k.na, abs=0.2)


@MET_FFMPEG
def test_zonder_lange_stilte_gaat_de_opname_ongewijzigd(tmp_path):
    audio = _opname(tmp_path, [("toon", 3), ("stil", 1), ("toon", 3)])
    assert asyncio.run(stilte.kort_in(audio)) is None


def test_zonder_ffmpeg_of_met_kapotte_opname_gaat_het_origineel(monkeypatch):
    assert asyncio.run(stilte.kort_in(b"")) is None
    if shutil.which("ffmpeg"):
        assert asyncio.run(stilte.kort_in(b"geen audio" * 200)) is None
    monkeypatch.setattr(stilte.shutil, "which", lambda naam: None)
    assert asyncio.run(stilte.kort_in(b"\x1aE\xdf\xa3" + b"0" * 2000)) is None


def test_staat_uit_zonder_register_of_instelling(monkeypatch):
    monkeypatch.setattr(register, "actief", lambda: False)
    assert asyncio.run(stilte.aan()) is False
    monkeypatch.setattr(register, "actief", lambda: True)

    async def rij(query, *args):
        return {"waarde": "aan"} if args[0] == stilte.INSTELLING else None
    monkeypatch.setattr(register, "fetchrow", rij)
    assert asyncio.run(stilte.aan()) is True

    async def kapot(query, *args):
        raise RuntimeError("weg")
    monkeypatch.setattr(register, "fetchrow", kapot)
    assert asyncio.run(stilte.aan()) is False


# ── In het consult ──

AUTH = {"type": "auth", "api_key": "geheim", "consent": True, "modus": "eu"}


def _consult_app(monkeypatch, ontvangen, aan, ingekort):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("ALLOWED_STT_PROVIDERS", "voxtral")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    monkeypatch.setattr(consult_live, "CONTROLE_OP_SECS", ())
    get_config.cache_clear()

    async def schakelaar():
        return aan

    async def kort_in(audio):
        return ingekort
    monkeypatch.setattr(stilte, "aan", schakelaar)
    monkeypatch.setattr(stilte, "kort_in", kort_in)

    async def transcribeer(audio, provider, language=None, naam="consult.webm"):
        ontvangen.append((audio, naam))
        return stt_service.TranscriptResult(
            raw_text="Keelpijn. Keel rood.", duration_secs=10.0, provider="voxtral",
            segments=[stt_service.TranscriptSegment("Keelpijn.", 0.0, 1.0, "spreker_speaker_1"),
                      stt_service.TranscriptSegment("Keel rood.", 6.0, 7.0, "spreker_speaker_0")])

    class Res:
        def __init__(self, t):
            self.t = t

        def to_dict(self):
            return {"segmenten": [[s.speaker, s.text] for s in self.t.segments]}

    async def verwerk(transcript, llm_provider=None, taal=None):
        return Res(transcript)

    async def nooit(url, api_key):
        raise AssertionError("niet naar Deepgram")

    app = FastAPI()

    @app.websocket("/ws")
    async def route(ws: WebSocket):
        await consult_live.volg_consult(ws, connect=nooit, verwerk=verwerk, transcribeer=transcribeer)
    return app


def _consult(app, nadictaat=None):
    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(AUTH))
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\x1aE\xdf\xa3opname")
        if nadictaat is not None:
            ws.send_text(json.dumps({"type": "nadictaat", "vanaf": nadictaat}))
        ws.send_text(json.dumps({"type": "stop"}))
        events = []
        while True:
            e = ws.receive_json()
            events.append(e)
            if e["type"] == "closed":
                return events


def test_consult_stuurt_de_ingekorte_opname_en_verschuift_het_nadictaat(monkeypatch):
    ontvangen = []
    k = stilte.Ingekort(audio=b"OggS-kort", voor=20.0, na=10.0, knippen=[(2.0, 12.0)])
    events = _consult(_consult_app(monkeypatch, ontvangen, True, k), nadictaat=15.0)
    assert ontvangen == [(b"OggS-kort", "consult.ogg")]
    uit = [e for e in events if e["type"] == "result"][0]["data"]
    # 15 s in the recording is 5 s in the shortened one: "Keel rood." at 6 s is the post-dictation
    assert uit["segmenten"][-1] == ["nadictaat", "Keel rood."]


def test_consult_zonder_schakelaar_stuurt_de_hele_opname(monkeypatch):
    ontvangen = []
    k = stilte.Ingekort(audio=b"OggS-kort", voor=20.0, na=10.0, knippen=[(2.0, 12.0)])
    _consult(_consult_app(monkeypatch, ontvangen, False, k))
    assert ontvangen == [(b"\x1aE\xdf\xa3opname", "consult.webm")]


def test_consult_als_inkorten_niets_oplevert_gaat_het_origineel(monkeypatch):
    ontvangen = []
    _consult(_consult_app(monkeypatch, ontvangen, True, None))
    assert ontvangen == [(b"\x1aE\xdf\xa3opname", "consult.webm")]


def test_alleen_de_controle_na_dertig_seconden():
    """Each check transcribes the recording from the start; at 2 and 5 minutes
    that billed most of the consult twice. The side panel's meter watches the rest."""
    assert consult_live.CONTROLE_OP_SECS == (30.0,)


# ── Spraaktest en Beheer ──

@pytest.fixture
def beheerder(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    get_config.cache_clear()

    async def aan():
        return True
    monkeypatch.setattr(beheer, "testgereedschap_aan", aan)
    logs = []

    async def log(door, handeling, praktijk_id=None, **details):
        logs.append((handeling, details))
    monkeypatch.setattr(register, "log", log)
    main.app.dependency_overrides[beheer.vereis_beheerder] = lambda: "dr-test"
    yield logs
    main.app.dependency_overrides.clear()
    get_config.cache_clear()


def test_spraaktest_vergelijkt_hele_en_ingekorte_opname(monkeypatch, beheerder):
    gezien = []

    async def kort_in(audio):
        return stilte.Ingekort(audio=b"OggS-kort", voor=600.0, na=420.0, knippen=[(1.0, 2.0)] * 12)

    async def een(naam, pad, taal):
        gezien.append(pad.name)
        tekst = "keelpijn sinds gisteren amoxicilline" if pad.suffix == ".ogg" else "keelpijn sinds gisteren"
        return {"aanbieder": naam, "tekst": tekst, "met_sprekers": "Spreker 1: " + tekst,
                "vaktermen": ["amoxicilline"] if "amoxi" in tekst else []}
    monkeypatch.setattr(stilte, "kort_in", kort_in)
    monkeypatch.setattr(spraaktest, "_een", een)
    monkeypatch.setattr(spraaktest.shutil, "which", lambda n: "/usr/bin/ffmpeg")

    r = TestClient(main.app).post("/api/v1/beheer/spraaktest/stilte", data={"taal": "nl", "tegen": "voxtral"},
                                  files={"audio": ("rollenspel.webm", b"\x1aE\xdf\xa3" + b"0" * 2000, "audio/webm")})
    assert r.status_code == 200, r.text
    b = r.json()
    assert sorted(gezien) == ["consult.ogg", "spraaktest.webm"]
    assert b["namen"] == ["Voxtral, hele opname", "Voxtral, stiltes ingekort"]
    assert b["stilte"]["minder_pct"] == 30.0 and b["stilte"]["knippen"] == 12
    assert b["alleen_voxtral"] == ["amoxicilline"] and b["alleen_deepgram"] == []
    # the SOEP step reads the same keys as in the normal comparison
    assert b["deepgram"]["met_sprekers"] and b["voxtral"]["met_sprekers"]
    assert beheerder[-1][0] == "beheer.spraaktest_stilte" and "tekst" not in json.dumps(beheerder[-1][1])


def test_spraaktest_meldt_als_er_niets_in_te_korten_valt(monkeypatch, beheerder):
    async def niets(audio):
        return None
    monkeypatch.setattr(stilte, "kort_in", niets)
    monkeypatch.setattr(spraaktest.shutil, "which", lambda n: "/usr/bin/ffmpeg")
    r = TestClient(main.app).post("/api/v1/beheer/spraaktest/stilte",
                                  files={"audio": ("a.webm", b"\x1aE\xdf\xa3" + b"0" * 2000, "audio/webm")})
    assert r.status_code == 400 and "niets in te korten" in r.json()["detail"]
    monkeypatch.setattr(spraaktest.shutil, "which", lambda n: None)
    r = TestClient(main.app).post("/api/v1/beheer/spraaktest/stilte",
                                  files={"audio": ("a.webm", b"\x1aE\xdf\xa3" + b"0" * 2000, "audio/webm")})
    assert r.status_code == 503 and "ffmpeg" in r.json()["detail"]


def test_beheerder_zet_stiltes_inkorten_aan_en_uit(monkeypatch, beheerder):
    opslag = {}
    monkeypatch.setenv("DATABASE_URL", "postgresql://test/test")

    async def execute(query, *args):
        opslag[args[0]] = args[1]
        return "OK"

    async def fetch(query, *args):
        return [{"sleutel": k, "waarde": v} for k, v in opslag.items()]

    async def fetchrow(query, *args):
        return {"waarde": opslag[args[0]]} if args[0] in opslag else None
    monkeypatch.setattr(register, "execute", execute)
    monkeypatch.setattr(register, "fetch", fetch)
    monkeypatch.setattr(register, "fetchrow", fetchrow)
    monkeypatch.setattr(register, "actief", lambda: True)
    api = TestClient(main.app)
    assert api.get("/api/v1/beheer/instellingen").json()["stilte_inkorten"] is False
    assert asyncio.run(stilte.aan()) is False
    r = api.put("/api/v1/beheer/instellingen", json={"stilte_inkorten": True})
    assert r.json()["stilte_inkorten"] is True and asyncio.run(stilte.aan()) is True
    api.put("/api/v1/beheer/instellingen", json={"stilte_inkorten": False})
    assert asyncio.run(stilte.aan()) is False
    handelingen = [h for h, _ in beheerder]
    assert "stilte_inkorten.aan" in handelingen and "stilte_inkorten.uit" in handelingen
