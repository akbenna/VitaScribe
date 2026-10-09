"""
Gedeelde configuratie voor AI-Consultassistent services.
Laadt settings uit environment variabelen met sensible defaults.
"""

import os
import secrets
import warnings
from dataclasses import dataclass, field
from pathlib import Path

# Laad .env bestand als het bestaat (development)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass


@dataclass
class DatabaseConfig:
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    database: str = os.getenv("POSTGRES_DB", "consultassistent")
    user: str = os.getenv("POSTGRES_USER", "ca_app")
    password: str = os.getenv("POSTGRES_PASSWORD", "")
    encryption_key: str = os.getenv("DB_ENCRYPTION_KEY", "")

    @property
    def dsn(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def async_dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RedisConfig:
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    password: str = os.getenv("REDIS_PASSWORD", "")

    @property
    def url(self) -> str:
        return f"redis://:{self.password}@{self.host}:{self.port}/0"


@dataclass
class WhisperConfig:
    model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    model_path: str = os.getenv("WHISPER_MODEL_PATH", "/models/whisper")
    device: str = os.getenv("WHISPER_DEVICE", "cuda")
    compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    language: str = os.getenv("WHISPER_LANGUAGE", "nl")
    beam_size: int = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
    # Medische context-biasing (zie shared/vocabulary.py)
    use_initial_prompt: bool = os.getenv("WHISPER_USE_INITIAL_PROMPT", "true").lower() == "true"
    use_hotwords: bool = os.getenv("WHISPER_USE_HOTWORDS", "true").lower() == "true"
    # Deterministische naberekening van het transcript via de woordenlijst
    postcorrect_transcript: bool = os.getenv("WHISPER_POSTCORRECT", "true").lower() == "true"
    # Pad naar geleerde (custom) correcties uit de feedbackloop
    custom_vocab_path: str = os.getenv(
        "WHISPER_CUSTOM_VOCAB_PATH", "/data/vocabulary/custom_vocabulary.json"
    )
    # WhisperX forced-alignment (Fase 3): preciezere woord-timestamps. Zwaar
    # (extra model + GPU); standaard uit, met fallback naar Faster-Whisper.
    use_forced_alignment: bool = os.getenv("WHISPER_USE_FORCED_ALIGNMENT", "false").lower() == "true"
    alignment_device: str = os.getenv("WHISPER_ALIGNMENT_DEVICE", "cuda")


@dataclass
class DiarizationConfig:
    enabled: bool = os.getenv("DIARIZATION_ENABLED", "true").lower() == "true"
    hf_token: str = os.getenv("HF_TOKEN", "")


@dataclass
class OllamaConfig:
    host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    fallback_model: str = os.getenv("OLLAMA_FALLBACK_MODEL", "")
    timeout: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))


@dataclass
class FewShotConfig:
    """Dynamische few-shot uit goedgekeurde SOEP's (zelflerende laag, niveau 2)."""
    enabled: bool = os.getenv("FEWSHOT_ENABLED", "true").lower() == "true"
    bank_path: str = os.getenv("FEWSHOT_BANK_PATH", "/data/fewshot/soep_examples.json")
    k: int = int(os.getenv("FEWSHOT_K", "3"))
    max_examples: int = int(os.getenv("FEWSHOT_MAX_EXAMPLES", "500"))


@dataclass
class CloudFallbackConfig:
    enabled: bool = os.getenv("CLOUD_FALLBACK_ENABLED", "false").lower() == "true"
    provider: str = os.getenv("CLOUD_FALLBACK_PROVIDER", "mistral")
    api_key: str = os.getenv("CLOUD_FALLBACK_API_KEY", "")
    api_url: str = os.getenv("CLOUD_FALLBACK_API_URL", "")
    confidence_threshold: float = float(os.getenv("CLOUD_FALLBACK_CONFIDENCE_THRESHOLD", "0.6"))


@dataclass
class HISExportConfig:
    default_target: str = os.getenv("HIS_DEFAULT_TARGET", "clipboard")
    cgm_api_url: str = os.getenv("CGM_API_URL", "")
    cgm_api_key: str = os.getenv("CGM_API_KEY", "")
    medicom_api_url: str = os.getenv("MEDICOM_API_URL", "")
    medicom_api_key: str = os.getenv("MEDICOM_API_KEY", "")
    fhir_base_url: str = os.getenv("FHIR_BASE_URL", "")
    export_timeout: int = int(os.getenv("HIS_EXPORT_TIMEOUT", "30"))


@dataclass
class AudioConfig:
    sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    format: str = os.getenv("AUDIO_FORMAT", "wav")
    max_duration_seconds: int = int(os.getenv("AUDIO_MAX_DURATION_SECONDS", "3600"))
    storage_path: Path = Path(os.getenv("AUDIO_STORAGE_PATH", "/data/audio"))


@dataclass
class AuditConfig:
    retention_years: int = int(os.getenv("AUDIT_LOG_RETENTION_YEARS", "5"))
    log_path: Path = Path(os.getenv("AUDIT_LOG_PATH", "/data/audit"))


@dataclass
class SecurityConfig:
    secret_key: str = os.getenv("APP_SECRET_KEY", "")

    def __post_init__(self):
        if not self.secret_key:
            if os.getenv("APP_ENV", "development") == "production":
                raise ValueError(
                    "APP_SECRET_KEY is verplicht in productie. "
                    "Stel een veilige sleutel in via environment variabelen."
                )
            self.secret_key = secrets.token_urlsafe(32)
            warnings.warn(
                "APP_SECRET_KEY niet ingesteld - gegenereerde tijdelijke sleutel. "
                "Stel een vaste sleutel in voor productie.",
                stacklevel=2,
            )
    cors_origins: list = field(default_factory=lambda: os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
    ).split(","))
    session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
    max_login_attempts: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))


@dataclass
class AppConfig:
    env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("APP_LOG_LEVEL", "INFO")
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    diarization: DiarizationConfig = field(default_factory=DiarizationConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    fewshot: FewShotConfig = field(default_factory=FewShotConfig)
    cloud_fallback: CloudFallbackConfig = field(default_factory=CloudFallbackConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    his_export: HISExportConfig = field(default_factory=HISExportConfig)

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


# Singleton
config = AppConfig()
