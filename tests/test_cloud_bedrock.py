"""Route A: Claude in Amazon Bedrock, EU region (PHI_LLM_PROVIDER=bedrock)."""

import asyncio
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from services.cloud_api import data_policy, dossiervraag, llm_service, main
from services.cloud_api.config import get_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "geheim")
    monkeypatch.setenv("PHI_LLM_PROVIDER", "bedrock")
    for name in ("BEDROCK_REGION", "BEDROCK_MODEL", "BEDROCK_SOEP_MODEL"):
        monkeypatch.delenv(name, raising=False)
    get_config.cache_clear()
    yield
    get_config.cache_clear()


class FakeMessages:
    """Records what would go to Bedrock and answers like the SDK does."""

    def __init__(self, text="", stop_reason="end_turn", events=None, error=None):
        self.calls = []
        self.text, self.stop_reason, self.events, self.error = text, stop_reason, events, error

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if kwargs.get("stream"):
            async def gen():
                for e in self.events:
                    yield e
            return gen()
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=self.text)],
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                  cache_read_input_tokens=0, cache_creation_input_tokens=10),
        )


@pytest.fixture
def fake(monkeypatch):
    holder = {}

    def install(**kw):
        msgs = FakeMessages(**kw)
        regions = []

        def client(region):
            regions.append(region)
            return SimpleNamespace(messages=msgs)
        monkeypatch.setattr(llm_service, "_bedrock_client", client)
        holder.update(msgs=msgs, regions=regions)
        return msgs
    install.holder = holder
    return install


def run(coro):
    return asyncio.run(coro)


def test_eu_check_fails_closed():
    assert llm_service.bedrock_eu_problem("eu-central-1", "eu.anthropic.claude-sonnet-5") is None
    assert "EU" in llm_service.bedrock_eu_problem("us-east-1", "eu.anthropic.claude-sonnet-5")
    assert "buiten de EU" in llm_service.bedrock_eu_problem("eu-central-1", "global.anthropic.claude-sonnet-5")
    assert "buiten de EU" in llm_service.bedrock_eu_problem("eu-west-1", "US.anthropic.claude-haiku-4-5")
    assert llm_service.bedrock_eu_problem("eu-west-1", "") == "geen model-ID ingesteld"


def test_non_eu_setting_sends_nothing(monkeypatch, fake):
    msgs = fake(text="x")
    monkeypatch.setenv("BEDROCK_SOEP_MODEL", "global.anthropic.claude-sonnet-5")
    get_config.cache_clear()
    with pytest.raises(ValueError, match="niets verstuurd"):
        run(llm_service.complete("sys", "vraag", provider="bedrock", quality=True))
    assert msgs.calls == []


def test_sonnet_json_without_structured_outputs(fake):
    msgs = fake(text='Hier is het:\n```json\n{"a": 1}\n```')
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
    out = run(llm_service.complete("SYSTEEM", "VRAAG", provider="bedrock", json_mode=True,
                                   max_tokens=500, cache_system=True, quality=True,
                                   json_schema=schema))
    assert json.loads(out) == {"a": 1}
    call = msgs.calls[0]
    assert fake.holder["regions"] == ["eu-central-1"]
    assert call["model"] == "eu.anthropic.claude-sonnet-5"
    # Bedrock has no structured outputs: the schema is an instruction in the
    # question, so the cached system prompt stays the same per patient.
    assert "format" not in call["output_config"] and call["output_config"]["effort"]
    assert call["system"] == [{"type": "text", "text": "SYSTEEM",
                               "cache_control": {"type": "ephemeral"}}]
    user = call["messages"][0]["content"]
    assert user.startswith("VRAAG") and '"required": ["a"]' in user
    assert call["max_tokens"] >= llm_service.MODERN_MIN_MAX_TOKENS
    assert "extra_body" not in call     # no temperature on Sonnet 5


def test_haiku_keeps_prefill_and_temperature(fake):
    msgs = fake(text='"b": 2}')
    out = run(llm_service.complete("s", "u", provider="bedrock", json_mode=True))
    assert json.loads(out) == {"b": 2}
    call = msgs.calls[0]
    assert call["model"] == "eu.anthropic.claude-haiku-4-5"
    assert call["messages"][-1] == {"role": "assistant", "content": "{"}
    assert call["extra_body"] == {"temperature": get_config().llm.temperature}
    assert "temperature" not in call


def test_refusal_and_errors_become_valueerror(fake):
    fake(text="", stop_reason="refusal")
    with pytest.raises(ValueError, match="weigerde"):
        run(llm_service.complete("s", "u", provider="bedrock"))
    resp = httpx2.Response(429, request=httpx2.Request("POST", "https://bedrock-mantle.eu-central-1.api.aws"))
    fake(error=anthropic.RateLimitError("te veel", response=resp, body=None))
    with pytest.raises(ValueError, match="429"):
        run(llm_service.complete("s", "u", provider="bedrock"))
    fake(error=anthropic.APIConnectionError(request=resp.request))
    with pytest.raises(ValueError, match="niet bereikbaar"):
        run(llm_service.complete("s", "u", provider="bedrock"))


def test_stream_from_bedrock(fake):
    ev = lambda t, **d: SimpleNamespace(type=t, delta=SimpleNamespace(**d))
    msgs = fake(events=[ev("content_block_delta", type="text_delta", text="Geachte "),
                        ev("content_block_delta", type="thinking_delta", text=None),
                        ev("content_block_delta", type="text_delta", text="collega"),
                        ev("message_delta", stop_reason="end_turn")])

    async def collect():
        return [p async for p in llm_service.stream_llm("bedrock", "sys", "brief", 1000, quality=True)]
    assert "".join(run(collect())) == "Geachte collega"
    assert msgs.calls[0]["stream"] is True and msgs.calls[0]["model"] == "eu.anthropic.claude-sonnet-5"
    # an EU model never runs on a practice's own key
    with pytest.raises(ValueError, match="sleutel van de server"):
        llm_service.stream_llm("bedrock", "s", "u", 10, api_key="eigen")


def test_policy_reports_eu_and_dossiervraag_uses_bedrock(fake):
    # PHI_LLM_PROVIDER applies to the claude mode; since 07-10-2026 the default mode is eu (Mistral)
    t = data_policy.zet_modus("claude")
    try:
        assert data_policy.phi_llm_provider() == "bedrock"
        assert data_policy.summary()["patient_data_llm_in_eu"] is True
    finally:
        data_policy.herstel_modus(t)
    msgs = fake(text=json.dumps({"antwoord": "Nitrofurantoïne.", "zekerheid": "expliciet",
                                 "bronnen": [], "let_op": ""}))
    dossier = "PATIËNT: J.J.\n== JOURNAAL ==\n14-02-2025 Cystitis, nitrofurantoïne 5 dagen."
    r = TestClient(main.app).post("/api/v1/dossier/vraag", headers={"X-API-Key": "geheim", "X-VitaScribe-Modus": "claude"},
                                  json={"dossier": dossier, "vraag": "Antibiotica?"})
    assert r.status_code == 200, r.text
    assert r.json()["zekerheid"] == "expliciet"
    call = msgs.calls[0]
    assert "nitrofurantoïne 5 dagen" in call["system"][0]["text"]
    assert '"zekerheid"' in call["messages"][0]["content"]   # schema as instruction
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert dossiervraag.ANTWOORD_SCHEMA["required"]


def test_health_deep_reports_bedrock(monkeypatch):
    monkeypatch.delenv("HEALTH_TOKEN", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    assert main._bedrock_status(get_config()) == "geen sleutel"
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    assert main._bedrock_status(get_config()) == "ok"
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    get_config.cache_clear()
    assert main._bedrock_status(get_config()).startswith("niet EU")


def test_letters_in_eu_follow_bedrock(monkeypatch):
    from services.cloud_api import praktijk_sleutels
    ident = SimpleNamespace(brieven_in_eu=True)
    t = data_policy.zet_modus("claude")   # the practice's letters-in-eu choice, in the claude mode
    try:
        assert run(praktijk_sleutels.kies_brieven(ident)) == ("bedrock", None)
        monkeypatch.setenv("PHI_LLM_PROVIDER", "anthropic")
        assert run(praktijk_sleutels.kies_brieven(ident)) == ("mistral", None)
    finally:
        data_policy.herstel_modus(t)
