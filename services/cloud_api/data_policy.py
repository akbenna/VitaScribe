"""
VitaScribe Cloud API - Data policy (AVG)

Which external service may process which kind of data. Decided with the
practice (24-09-2026, changed 28-09-2026):

- Text or images that can identify a patient (dictation, consultation
  transcript, dossier screenshots, patient instructions) go to Claude
  (Anthropic, US) under Anthropic's commercial terms: not used for training.
  Mistral (EU) was the first choice but could not carry the load; it can be
  switched back with PHI_LLM_PROVIDER=mistral once a paid plan is in place.
- Letters are pseudonymised in the browser and on the server; they may go to
  the letters provider (Claude by default) once the agreements are in place
  (DPA + SCC's, zero data retention).
- Speech goes to Deepgram's EU endpoint with the Model Improvement Program
  switched off (mip_opt_out), so audio is not kept or used for training.
- The browser cannot override these choices; an unknown or non-allowed
  provider falls back to the configured one.

Settings (environment):
  PHI_LLM_PROVIDER        default "anthropic"
  LETTERS_LLM_PROVIDER    default "anthropic"
  ALLOWED_STT_PROVIDERS   default "deepgram"
  CLINICAL_DECISION_SUPPORT  default "false": no clinical suggestions (MDR)
"""

from __future__ import annotations

import os
from typing import Optional

import structlog

logger = structlog.get_logger()

EU_PROVIDERS = {"mistral"}


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().lower()


def phi_llm_provider(requested: Optional[str] = None) -> str:
    """Language model for data that can identify a patient."""
    configured = _env("PHI_LLM_PROVIDER", "anthropic")
    if requested and requested.lower() != configured:
        logger.info("policy.provider_override_ignored", requested=requested, used=configured)
    return configured


def letters_llm_provider() -> str:
    """Language model for pseudonymised letters."""
    return _env("LETTERS_LLM_PROVIDER", "anthropic")


def stt_provider(requested: Optional[str] = None) -> str:
    """Speech-to-text provider; only the allowed ones (default: Deepgram EU)."""
    allowed = [p.strip() for p in _env("ALLOWED_STT_PROVIDERS", "deepgram").split(",") if p.strip()]
    if requested and requested.lower() in allowed:
        return requested.lower()
    if requested:
        logger.info("policy.stt_override_ignored", requested=requested, used=allowed[0])
    return allowed[0]


def clinical_decision_support() -> bool:
    """Clinical suggestions (alarm symptoms, NHG advice) are off: that would
    make the software a medical device (MDR rule 11). Only documentation
    completeness is reported."""
    return _env("CLINICAL_DECISION_SUPPORT", "false") == "true"


def summary() -> dict:
    """For /health and the settings page: where data goes."""
    return {
        "patient_data_llm": phi_llm_provider(),
        "patient_data_llm_in_eu": phi_llm_provider() in EU_PROVIDERS,
        "letters_llm": letters_llm_provider(),
        "stt": stt_provider(),
        "stt_eu_endpoint": True,
        "stt_training_opt_out": True,
        "clinical_decision_support": clinical_decision_support(),
    }
