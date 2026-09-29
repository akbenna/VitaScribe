"""Brieven (informatiebrief / verwijsbrief) via de VitaScribe-server."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import letters, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def api():
    return TestClient(main.app)


H = {"X-API-Key": "geheim"}
DOSSIER = "PATIËNT: J.J.\n== JOURNAAL ==\nLage rugpijn sinds 3 mnd, fysiotherapie gestart."


def fake_stream(pieces, seen=None):
    async def _stream(provider, system, user, max_tokens, quality=False, api_key=None):
        if seen is not None:
            seen.append({"provider": provider, "system": system, "user": user,
                         "quality": quality, "max_tokens": max_tokens, "api_key": api_key})
        for p in pieces:
            yield p
    return _stream


def test_privacy_safety_net_removes_direct_identifiers():
    t = "BSN 123456789, mail jan@voorbeeld.nl, tel 06-12345678 en 0475 123456, NL91ABNA0417164300"
    out = letters.privacy_safety_net(t)
    for secret in ("123456789", "jan@voorbeeld.nl", "12345678", "123456", "NL91ABNA"):
        assert secret not in out
    # medische getallen blijven staan
    assert letters.privacy_safety_net("RR 140/90, Hb 8.4, 500 mg 3dd") == "RR 140/90, Hb 8.4, 500 mg 3dd"


def test_informatiebrief_requires_consent(api):
    resp = api.post("/api/v1/letters/generate", headers=H,
                    json={"kind": "informatiebrief", "aanvrager": "uwv", "dossier": DOSSIER})
    assert resp.status_code == 400
    assert "toestemming" in resp.json()["detail"]


def test_informatiebrief_streams_and_follows_knmg(api):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Geachte ", "collega,"], seen)):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "informatiebrief", "aanvrager": "uwv", "toestemming": True,
            "dossier": DOSSIER + " BSN 123456789", "vraag": "1. Welke diagnose?",
            "initialen": "J.J.",
        })
    assert resp.status_code == 200
    assert resp.text == "Geachte collega,"
    call = seen[0]
    assert call["quality"] is True
    assert "GEEN oordeel" in call["system"] and "UWV" in call["system"]
    assert "123456789" not in call["user"] and "1. Welke diagnose?" in call["user"]


def test_verwijzing_uses_fast_model_and_needs_reason(api):
    resp = api.post("/api/v1/letters/generate", headers=H,
                    json={"kind": "verwijzing", "dossier": DOSSIER, "specialisme": "orthopeed"})
    assert resp.status_code == 400
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Geachte collega,"], seen)):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "verwijzing", "dossier": DOSSIER, "specialisme": "orthopedisch chirurg",
            "urgentie": "regulier", "reden": "Graag beoordeling persisterende rugpijn",
        })
    assert resp.status_code == 200
    assert seen[0]["quality"] is False
    assert "orthopedisch chirurg" in seen[0]["user"]


def test_provider_error_before_stream_gives_502(api):
    async def failing(provider, system, user, max_tokens, quality=False, api_key=None):
        raise ValueError("ANTHROPIC_API_KEY niet geconfigureerd.")
        yield ""  # pragma: no cover
    with patch.object(letters.llm_service, "stream_llm", failing):
        resp = api.post("/api/v1/letters/generate", headers=H, json={
            "kind": "verwijzing", "dossier": DOSSIER, "reden": "x"})
    assert resp.status_code == 502


def test_extract_reads_image_and_filters(api):
    seen = []
    with patch.object(letters.llm_service, "stream_llm", fake_stream(["Journaal\nBSN 123456789 hoofdpijn"], seen)):
        resp = api.post("/api/v1/letters/extract", headers=H,
                        json={"kind": "dossier", "media_type": "image/png", "data": "iVBORw0KGgoAAAANS"})
    assert resp.status_code == 200
    assert "123456789" not in resp.json()["text"] and "hoofdpijn" in resp.json()["text"]
    # screenshots can identify the patient: the patient-data model, in its image format
    assert seen[0]["provider"] == "anthropic"
    assert seen[0]["user"][0]["type"] == "image"


def test_letters_require_api_key(api):
    resp = api.post("/api/v1/letters/generate", json={"kind": "verwijzing", "dossier": DOSSIER, "reden": "x"})
    assert resp.status_code in (401, 403)
