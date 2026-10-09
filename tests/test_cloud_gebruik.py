"""Gebruiksregels voor de kostencontrole: per dienst hoeveel, nooit wat."""

import pytest
from structlog.testing import capture_logs

from services.cloud_api import llm_service, stt_service
from services.cloud_api.config import get_config


@pytest.mark.asyncio
async def test_spraak_logt_seconden_zonder_tekst(monkeypatch):
    async def voxtral(audio, language=None, naam="", diarize=True):
        return stt_service.TranscriptResult(raw_text="Ik heb hoofdpijn sinds gisteren.", duration_secs=12.34,
                                            provider="voxtral")
    monkeypatch.setattr(stt_service, "_transcribe_voxtral", voxtral)
    with capture_logs() as logs:
        await stt_service.transcribe_eu(b"geluid", "nl", diarize=False, provider="voxtral")
    regel = [l for l in logs if l["event"] == "stt.usage"]
    assert regel == [{"event": "stt.usage", "provider": "voxtral", "seconden": 12.3, "soort": "beurt",
                      "log_level": "info"}]
    assert "hoofdpijn" not in str(logs)


@pytest.mark.asyncio
async def test_mistral_logt_tokens(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock, patch
    monkeypatch.setenv("MISTRAL_API_KEY", "m")
    get_config.cache_clear()
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"choices": [{"message": {"content": "Hoofdpijn."}}],
                                        "usage": {"prompt_tokens": 120, "completion_tokens": 8}})
    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch.object(llm_service.httpx, "AsyncClient", return_value=client), capture_logs() as logs:
        await llm_service.complete("sys", "usr", provider="mistral")
    regel = [l for l in logs if l["event"] == "llm.mistral.usage"][0]
    assert regel["input_tokens"] == 120 and regel["output_tokens"] == 8 and "Hoofdpijn" not in str(logs)
    get_config.cache_clear()
