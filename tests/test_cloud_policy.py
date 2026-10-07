"""AVG / NEN 7513 / KNMG: sleutels per gebruiker, gebruikslog, toestemming opname."""

import json

import pytest
from fastapi.testclient import TestClient

from services.cloud_api import audit, auth, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("API_USERS", "dr.bennaghmouch:sleutel-a,assistente:sleutel-b")
    monkeypatch.setenv("API_KEYS", "oud-gedeeld")
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_keys_map_to_users():
    assert auth.user_for_key("sleutel-a") == "dr.bennaghmouch"
    assert auth.user_for_key("sleutel-b") == "assistente"
    assert auth.user_for_key("oud-gedeeld") == "gedeeld"
    assert auth.user_for_key("fout") is None


def test_server_without_keys_fails_closed(monkeypatch):
    monkeypatch.delenv("API_USERS")
    monkeypatch.delenv("API_KEYS")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VITASCRIBE_OPEN", raising=False)
    get_config.cache_clear()
    assert auth.user_for_key("wat-dan-ook") is None
    r = TestClient(main.app).get("/api/v1/providers", headers={"X-API-Key": "wat-dan-ook"})
    assert r.status_code == 503
    monkeypatch.setenv("VITASCRIBE_OPEN", "1")
    assert auth.user_for_key("") == "dev"


def test_audit_log_keeps_no_content(tmp_path):
    audit.log_event("dr.x", "letters.generate", kind="verwijzing", tekst="Jan de Vries BSN 123456789",
                    chars=5000, status="x" * 100)
    line = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert line["user"] == "dr.x" and line["action"] == "letters.generate" and line["chars"] == 5000
    assert "tekst" not in line and "status" not in line   # not whitelisted / too long
    assert "Vries" not in json.dumps(line)


def test_consult_recording_requires_consent(tmp_path):
    client = TestClient(main.app)
    resp = client.post("/api/v1/consult/process", headers={"X-API-Key": "sleutel-a"},
                       files={"audio": ("c.webm", b"x" * 100, "audio/webm")})
    assert resp.status_code == 400 and "Toestemming" in resp.json()["detail"]
    log = (tmp_path / "audit.jsonl").read_text()
    assert "consult.refused" in log and "dr.bennaghmouch" in log


def test_health_reports_data_policy():
    # since 07-10-2026 the default mode is eu: without a header nothing leaves EU companies
    body = TestClient(main.app).get("/health").json()
    assert body["data_policy"]["modus"] == "eu"
    assert body["data_policy"]["patient_data_llm"] == "mistral"
    assert body["data_policy"]["patient_data_llm_in_eu"] is True
    body = TestClient(main.app).get("/health", headers={"X-VitaScribe-Modus": "claude"}).json()
    assert body["data_policy"]["modus"] == "claude"
    assert body["data_policy"]["patient_data_llm"] == "anthropic"
    assert body["data_policy"]["patient_data_llm_in_eu"] is False   # Claude (VS), besluit 28-09-2026


def test_patient_instructions_use_patient_model_and_translate(monkeypatch):
    from unittest.mock import AsyncMock, patch
    from services.cloud_api import patient_info
    out = json.dumps({"nl": "Wat gaat u doen\nNeem amoxicilline 500 mg, 3 keer per dag, 7 dagen.",
                      "vertaling": "What will you do ..."})
    with patch.object(patient_info.llm_service, "complete", AsyncMock(return_value=out)) as llm:
        resp = TestClient(main.app).post("/api/v1/patient-instructions",
                                         headers={"X-API-Key": "sleutel-a", "X-VitaScribe-Modus": "claude"},
                                         json={"e": "pneumonie", "p": "amoxicilline 3dd 500 mg 7d", "taal": "en"})
    assert resp.status_code == 200
    assert resp.json()["taal"] == "Engels" and resp.json()["vertaling"]
    assert llm.await_args.kwargs["provider"] == "anthropic"
    assert "Voeg geen adviezen" in llm.await_args.kwargs["system_prompt"]
    bad = TestClient(main.app).post("/api/v1/patient-instructions", headers={"X-API-Key": "sleutel-a"},
                                    json={"p": "x x x", "taal": "zz"})
    assert bad.status_code == 400
