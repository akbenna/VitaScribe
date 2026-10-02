"""
VitaScribe Cloud API - Configuration

All settings via environment variables. Supports multiple STT and LLM providers
with Deepgram + Mistral as defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class STTConfig:
    """Speech-to-text provider configuration."""

    default_provider: str = "deepgram"
    groq_api_key: str = ""
    groq_model: str = "whisper-large-v3-turbo"
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    deepgram_language: str = "nl"
    openai_api_key: str = ""
    openai_model: str = "whisper-1"
    # Mistral Voxtral (France): batch transcription with speaker labels. Uses
    # the Mistral key of the language model (MISTRAL_API_KEY).
    voxtral_model: str = "voxtral-mini-latest"


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration."""

    default_provider: str = "anthropic"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    # SOEP, letters and reading screenshots need the stronger (multimodal) model.
    mistral_quality_model: str = "mistral-medium-latest"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    # SOEP generation needs medical reasoning (diagnosis naming, ICPC); the
    # light tasks (cleanup, nazorg) stay on the cheaper, faster model.
    anthropic_soep_model: str = "claude-sonnet-5"
    # Thinking depth on Sonnet 5+: low | medium | high (latency vs. reasoning).
    anthropic_effort: str = "medium"
    # Claude in Amazon Bedrock (AWS-run, EU region): the same models, but
    # processed in the EU and without Anthropic in the chain. Credentials come
    # from the standard AWS variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY).
    # Model IDs carry the EU inference profile; check them in the Bedrock
    # console of the region, they differ per model version.
    bedrock_region: str = "eu-central-1"
    bedrock_model: str = "eu.anthropic.claude-haiku-4-5"
    bedrock_soep_model: str = "eu.anthropic.claude-sonnet-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    # OpenAI only runs on a practice's own key, and only for letters.
    openai_model: str = "gpt-4.1-mini"
    openai_quality_model: str = "gpt-4.1"
    temperature: float = 0.1
    max_tokens: int = 2048


@dataclass(frozen=True)
class DictationConfig:
    """Live dictation (streaming STT) configuration."""

    deepgram_url: str = "wss://api.eu.deepgram.com/v1/listen"
    deepgram_model: str = "nova-3"
    deepgram_language: str = "nl"
    endpointing_ms: int = 300
    keyterms_enabled: bool = True
    max_seconds: int = 600


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False
    cors_origins: str = "*"
    api_keys: str = ""
    max_audio_size_mb: int = 50
    temp_dir: str = "/tmp/vitascribe"

    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    dictation: DictationConfig = field(default_factory=DictationConfig)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Load configuration from environment variables."""
    return AppConfig(
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", os.getenv("API_PORT", "8002"))),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        cors_origins=os.getenv("CORS_ORIGINS", "*"),
        api_keys=os.getenv("API_KEYS", ""),
        max_audio_size_mb=int(os.getenv("MAX_AUDIO_MB", "50")),
        temp_dir=os.getenv("TEMP_DIR", "/tmp/vitascribe"),
        stt=STTConfig(
            default_provider=os.getenv("STT_PROVIDER", "deepgram"),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            groq_model=os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            deepgram_model=os.getenv("DEEPGRAM_MODEL", "nova-3"),
            deepgram_language=os.getenv("DEEPGRAM_LANGUAGE", "nl"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_STT_MODEL", "whisper-1"),
            voxtral_model=os.getenv("VOXTRAL_MODEL", "voxtral-mini-latest"),
        ),
        llm=LLMConfig(
            default_provider=os.getenv("LLM_PROVIDER", "anthropic"),
            mistral_api_key=os.getenv("MISTRAL_API_KEY", ""),
            mistral_model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
            mistral_quality_model=os.getenv("MISTRAL_QUALITY_MODEL", "mistral-medium-latest"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            anthropic_soep_model=os.getenv("ANTHROPIC_SOEP_MODEL", "claude-sonnet-5"),
            anthropic_effort=os.getenv("ANTHROPIC_EFFORT", "medium"),
            bedrock_region=os.getenv("BEDROCK_REGION", "eu-central-1"),
            bedrock_model=os.getenv("BEDROCK_MODEL", "eu.anthropic.claude-haiku-4-5"),
            bedrock_soep_model=os.getenv("BEDROCK_SOEP_MODEL", "eu.anthropic.claude-sonnet-5"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            openai_model=os.getenv("OPENAI_LETTERS_MODEL", "gpt-4.1-mini"),
            openai_quality_model=os.getenv("OPENAI_LETTERS_QUALITY_MODEL", "gpt-4.1"),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        ),
        dictation=DictationConfig(
            deepgram_url=os.getenv("DICTATION_DEEPGRAM_URL", "wss://api.eu.deepgram.com/v1/listen"),
            deepgram_model=os.getenv("DICTATION_DEEPGRAM_MODEL", "nova-3"),
            deepgram_language=os.getenv("DICTATION_LANGUAGE", "nl"),
            endpointing_ms=int(os.getenv("DICTATION_ENDPOINTING_MS", "300")),
            keyterms_enabled=os.getenv("DICTATION_KEYTERMS", "true").lower() == "true",
            max_seconds=int(os.getenv("DICTATION_MAX_SECONDS", "600")),
        ),
    )
