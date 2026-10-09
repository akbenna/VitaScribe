"""Telefoon als tweede apparaat: koppelen, berichten, tolkbeurt namens de arts, foto."""

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import llm_service, main, telefoon, tolk
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_USERS", "dr_a:sleutel-a,dr_b:sleutel-b")
    monkeypatch.delenv("API_KEYS", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "m")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "d")
    get_config.cache_clear()
    telefoon._koppelingen.clear()
    yield
    telefoon._koppelingen.clear()
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


A = {"X-API-Key": "sleutel-a"}
B = {"X-API-Key": "sleutel-b"}
EU_A = {**A, "X-VitaScribe-Modus": "eu"}


def koppel(api, headers=A, **body):
    r = api.post("/api/v1/telefoon/koppel", headers=headers, json={"taal": "ar-MA", "toestemming": True, **body})
    assert r.status_code == 200, r.text
    return r.json()["geheim"]


def tel(geheim):
    return {"X-VitaScribe-Koppel": geheim}


def test_koppelen_en_berichten_heen_en_weer(api):
    g = koppel(api)
    assert len(g) >= 32
    # The phone says hello; the panel hears it.
    h = api.post("/api/v1/telefoon/hallo", headers=tel(g)).json()
    assert h["taal"]["code"] == "ar-MA" and h["toestemming"] is True and h["rtl"] is True
    r = api.get("/api/v1/telefoon/paneel/ontvang?wacht=0", headers={**A, **tel(g)}).json()
    assert r["berichten"] == [{"type": "verbonden", "data": {"eerste": True}}]
    # Panel -> phone: read this aloud.
    assert api.post("/api/v1/telefoon/paneel", headers={**A, **tel(g)},
                    json={"type": "spreek", "data": {"tekst": "Salam", "taal": "ar-MA"}}).json()["telefoon"] is True
    assert api.get("/api/v1/telefoon/ontvang?wacht=0", headers=tel(g)).json()["berichten"][0]["type"] == "spreek"
    # Picked up once: gone.
    assert api.get("/api/v1/telefoon/ontvang?wacht=0", headers=tel(g)).json()["berichten"] == []
    # Status from the phone.
    api.post("/api/v1/telefoon/status", headers=tel(g), json={"status": "luistert"})
    assert api.get("/api/v1/telefoon/paneel/ontvang?wacht=0", headers={**A, **tel(g)}).json()["berichten"] == [
        {"type": "status", "data": {"status": "luistert"}}]
    assert api.post("/api/v1/telefoon/status", headers=tel(g), json={"status": "iets"}).status_code == 400
    assert api.post("/api/v1/telefoon/paneel", headers={**A, **tel(g)}, json={"type": "rm -rf"}).status_code == 400


def test_geheim_nodig_en_alleen_voor_de_eigen_arts(api):
    g = koppel(api)
    assert api.post("/api/v1/telefoon/hallo").status_code == 410
    assert api.post("/api/v1/telefoon/hallo", headers=tel("raden")).status_code == 410
    # Another doctor cannot read or send on this pairing.
    assert api.get("/api/v1/telefoon/paneel/ontvang?wacht=0", headers={**B, **tel(g)}).status_code == 403
    # Without the API key the panel endpoints are closed.
    assert api.get("/api/v1/telefoon/paneel/ontvang?wacht=0", headers=tel(g)).status_code in (401, 403)
    # The secret never goes into a URL the server logs: the page gets it after the #.
    assert api.post("/api/v1/telefoon/koppel", headers=A, json={}).json()["pad"].startswith("/m#")


def test_ontkoppelen_en_verlopen(api, monkeypatch):
    g = koppel(api)
    api.delete("/api/v1/telefoon/koppel", headers={**A, **tel(g)})
    # The phone still hears that it was stopped ...
    assert api.get("/api/v1/telefoon/ontvang?wacht=0", headers=tel(g)).json()["berichten"][0]["type"] == "stop"
    # ... and a turn is no longer allowed (no consent any more).
    g2 = koppel(api)
    k = telefoon._koppelingen[g2]
    k.laatst -= telefoon.MAX_STIL + 1
    assert api.post("/api/v1/telefoon/hallo", headers=tel(g2)).status_code == 410


def test_hooguit_drie_koppelingen_per_arts(api):
    gs = [koppel(api) for _ in range(5)]
    assert [g in telefoon._koppelingen for g in gs] == [False, False, True, True, True]
    koppel(api, headers=B)
    assert len(telefoon._koppelingen) == 4


def test_onbekende_taal_geweigerd(api):
    assert api.post("/api/v1/telefoon/koppel", headers=A, json={"taal": "xx"}).status_code == 400


def test_beurt_van_de_telefoon_namens_de_arts_in_zijn_modus(api, monkeypatch):
    stt = []

    async def voxtral(audio, language=None, naam="", diarize=True):
        stt.append(language)
        from services.cloud_api.stt_service import TranscriptResult
        return TranscriptResult(raw_text="Heeft u koorts?", provider="voxtral")
    monkeypatch.setattr(tolk.stt_service, "_transcribe_voxtral", voxtral)
    gezien = []

    async def complete(system=None, user=None, provider=None, **kw):
        gezien.append(provider)
        return json.dumps({"spreker": "arts", "origineel": "Heeft u koorts?", "vertaling": "واش عندك السخانة؟",
                           "terugvertaling": "Heeft u koorts?", "onzeker": False, "twijfel": ""})
    monkeypatch.setattr(llm_service, "complete", complete)
    g = koppel(api, headers=EU_A)   # paired in the EU mode
    r = api.post("/api/v1/telefoon/beurt", headers=tel(g), data={"spreker": "auto"},
                 files={"audio": ("beurt.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 200, r.text
    assert r.json()["vertaling"] == "واش عندك السخانة؟"
    # The phone sent no mode header; the pairing's EU mode was used: Voxtral and Mistral.
    # Twee vaste talen (Nederlands en Arabisch), niet uit alle talen kiezen.
    assert sorted(stt) == ["ar", "nl"] and gezien == ["mistral"]
    # The panel received the same turn.
    p = api.get("/api/v1/telefoon/paneel/ontvang?wacht=0", headers={**EU_A, **tel(g)}).json()["berichten"]
    assert p[-1]["type"] == "beurt" and p[-1]["data"]["spreker"] == "arts"


def test_beurt_zonder_toestemming_of_zonder_tolk_geweigerd(api):
    g = koppel(api, toestemming=False)
    r = api.post("/api/v1/telefoon/beurt", headers=tel(g), files={"audio": ("b.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 400 and "Toestemming" in r.json()["detail"]
    g2 = koppel(api, taal=None)
    r = api.post("/api/v1/telefoon/beurt", headers=tel(g2), files={"audio": ("b.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 400


def test_foto_naar_het_paneel(api):
    g = koppel(api, taal=None)
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    assert api.post("/api/v1/telefoon/foto", headers=tel(g), files={"foto": ("f.jpg", jpeg, "image/jpeg")}).json() == {"ok": True}
    b = api.get("/api/v1/telefoon/paneel/ontvang?wacht=0", headers={**A, **tel(g)}).json()["berichten"][0]
    assert b["type"] == "foto" and base64.b64decode(b["data"]["data"]) == jpeg
    assert api.post("/api/v1/telefoon/foto", headers=tel(g), files={"foto": ("f.txt", b"x", "text/plain")}).status_code == 400


def test_spreek_met_serverstem(api, monkeypatch):
    async def stem(tekst, taal, geslacht="vrouw"):
        return b"ID3mp3" if taal.code == "de" else None
    monkeypatch.setattr(tolk, "tekst_naar_spraak", stem)
    g = koppel(api)
    r = api.post("/api/v1/telefoon/spreek", headers=tel(g), json={"tekst": "Guten Tag", "taal": "de"})
    assert r.status_code == 200 and r.content == b"ID3mp3"
    assert api.post("/api/v1/telefoon/spreek", headers=tel(g), json={"tekst": "x", "taal": "tr"}).status_code == 404


def test_long_poll_wacht_tot_er_iets_is():
    async def scenario():
        k = telefoon.Koppeling(geheim="g", ident=None, label="x", modus="eu", eigenaar="", taal=None, toestemming=False)
        taak = asyncio.create_task(telefoon._ontvang(k, "telefoon", 5))
        await asyncio.sleep(0.05)
        assert not taak.done()
        telefoon._stuur(k, "telefoon", {"type": "spreek", "data": {}})
        return await asyncio.wait_for(taak, 1)
    assert asyncio.run(scenario()) == [{"type": "spreek", "data": {}}]


def test_pagina_en_scripts(api):
    r = api.get("/m")
    assert r.status_code == 200 and "VitaScribe" in r.text
    assert "camera=(self)" in r.headers["permissions-policy"] and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert api.get("/m/telefoon.js").status_code == 200
    # The phone uses the same voice detection as the extension: one source.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (root / "services/cloud_api/static/tolk.js").read_bytes() == (root / "chrome-extension/lib/tolk.js").read_bytes()
