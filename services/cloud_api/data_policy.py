"""
VitaScribe Cloud API - Data policy (AVG)

Which external service may process which kind of data. Decided with the
practice (24-09-2026, changed 28-09-2026):

- Text or images that can identify a patient (dictation, consultation
  transcript, dossier screenshots, patient instructions) go to Claude
  (Anthropic, US) under Anthropic's commercial terms: not used for training.
  Mistral (EU) was the first choice but could not carry the load; it can be
  switched back with PHI_LLM_PROVIDER=mistral once a paid plan is in place.
- Route A (01-10-2026): PHI_LLM_PROVIDER=bedrock sends the same text to the
  same Claude models in Amazon Bedrock, EU region (eu-central-1, EU inference
  profile). AWS runs the models; Anthropic has no access to prompts or
  answers and is then not a (sub)processor. The server refuses to send when
  the region or a model ID can route outside the EU (fail closed).
- Letters are pseudonymised in the browser and on the server; they may go to
  the letters provider (Claude by default) once the agreements are in place
  (DPA + SCC's, zero data retention).
- Speech goes to Deepgram's EU endpoint with the Model Improvement Program
  switched off (mip_opt_out), so audio is not kept or used for training.
- The browser cannot override these choices; an unknown or non-allowed
  provider falls back to the configured one.

Two modes (02-10-2026). The doctor chooses, per request, in the extension
(header X-VitaScribe-Modus, or "modus" in the WebSocket auth message). The
server always follows that choice and never changes it; it may only advise.
If the eu mode cannot run (no Mistral key), the request fails with a message:
it never falls back to Claude on its own. Without a choice: claude.

- "claude" (default): everything above, with all features (live dictation,
  question suggestions).
- "eu" (formal mode): nothing leaves EU companies. Patient text and letters go
  to EU_LLM_PROVIDER (Mistral by default; bedrock also counts as EU), consults
  to Voxtral after the consult. A practice's own US keys are not used. Live
  dictation is refused (it needs Deepgram) and question suggestions cannot
  run (they need text during the consult).

Settings (environment):
  PHI_LLM_PROVIDER        default "anthropic"  (anthropic | bedrock | mistral)
  LETTERS_LLM_PROVIDER    default "anthropic"
  BEDROCK_REGION, BEDROCK_MODEL, BEDROCK_SOEP_MODEL and the AWS credentials
                          for route A (config.py)
  EU_LLM_PROVIDER         default "mistral" (mistral | bedrock), for the eu mode
  ALLOWED_STT_PROVIDERS   default "deepgram". "voxtral": consults (live and
                          uploaded) go to Mistral Voxtral (EU) after the consult;
                          dictation stays on Deepgram (needs live text).
  CLINICAL_DECISION_SUPPORT  default "false": no clinical suggestions (MDR).
                          Only in the claude mode; never in the eu mode.
                          "true" on the practice's own server: red flags in the
                          report and question suggestions during the live
                          consult, the latter only for doctors who switch them
                          on in the extension (vraagsuggesties.py).
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar, Token
from typing import List, Optional

import structlog

logger = structlog.get_logger()

EU_PROVIDERS = {"mistral", "bedrock"}
MODI = ("claude", "eu")

# The mode of the request being handled (set per HTTP request by middleware,
# per WebSocket after authentication).
_modus: ContextVar[Optional[str]] = ContextVar("vs_modus", default=None)


def _env(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().lower()


def toegestane_modi() -> List[str]:
    """Both modes, always: the doctor decides, not the server."""
    return list(MODI)


def kies_modus(requested: Optional[str] = None) -> str:
    """The doctor's choice; only an unknown value means the default (claude)."""
    gevraagd = (requested or "").strip().lower()
    return gevraagd if gevraagd in MODI else "claude"


def eu_gereed() -> Optional[str]:
    """None if the eu mode can run, otherwise why not (for advice, never to switch)."""
    from .config import get_config
    if eu_llm_provider() == "mistral" and not get_config().llm.mistral_api_key:
        return "Op de server is geen Mistral-sleutel ingesteld; in de EU-modus mislukken aanvragen tot die er is."
    return None


def zet_modus(requested: Optional[str] = None) -> Token:
    return _modus.set(kies_modus(requested))


def herstel_modus(token: Token) -> None:
    _modus.reset(token)


def modus() -> str:
    return _modus.get() or "claude"


def eu_modus() -> bool:
    return modus() == "eu"


def eu_llm_provider() -> str:
    gekozen = _env("EU_LLM_PROVIDER", "mistral")
    return gekozen if gekozen in EU_PROVIDERS else "mistral"


def phi_llm_provider(requested: Optional[str] = None) -> str:
    """Language model for data that can identify a patient."""
    configured = eu_llm_provider() if eu_modus() else _env("PHI_LLM_PROVIDER", "anthropic")
    if requested and requested.lower() != configured:
        logger.info("policy.provider_override_ignored", requested=requested, used=configured)
    return configured


def letters_llm_provider() -> str:
    """Language model for pseudonymised letters."""
    if eu_modus():
        return eu_llm_provider()
    return _env("LETTERS_LLM_PROVIDER", "anthropic")


def stt_provider(requested: Optional[str] = None) -> str:
    """Speech-to-text provider; only the allowed ones (default: Deepgram EU).
    In the eu mode always Voxtral (Mistral, EU)."""
    if eu_modus():
        return "voxtral"
    allowed = [p.strip() for p in _env("ALLOWED_STT_PROVIDERS", "deepgram").split(",") if p.strip()]
    if requested and requested.lower() in allowed:
        return requested.lower()
    if requested:
        logger.info("policy.stt_override_ignored", requested=requested, used=allowed[0])
    return allowed[0]


def clinical_decision_support() -> bool:
    """Clinical suggestions (question suggestions, NHG policy check, Thuisarts
    topics) make the software a medical device (MDR rule 11). Off unless the
    server allows it; the doctor then still switches each one on in the
    extension. Without it only documentation completeness and the medication
    name check are reported. Never in the eu mode: that is the formal mode,
    documentation only (decided with the practice, 02-10-2026)."""
    if eu_modus():
        return False
    return _env("CLINICAL_DECISION_SUPPORT", "false") == "true"


def econsult_nhg() -> bool:
    """NHG input in an e-consult answer (advice the doctor did not give) is
    clinical decision support too. Outside the eu mode it follows
    CLINICAL_DECISION_SUPPORT. In the eu mode it stays off unless the practice
    explicitly allows this one use (ECONSULT_NHG_IN_EU=true); the doctor then
    still ticks it per e-consult, it is never on by default."""
    if eu_modus():
        return _env("ECONSULT_NHG_IN_EU", "false") == "true"
    return clinical_decision_support()


def summary() -> dict:
    """For /health and the settings page: where data goes."""
    return {
        "modus": modus(),
        "modi": toegestane_modi(),
        "patient_data_llm": phi_llm_provider(),
        "patient_data_llm_in_eu": phi_llm_provider() in EU_PROVIDERS,
        "letters_llm": letters_llm_provider(),
        "stt": stt_provider(),
        # Voxtral: an EU company in the EU; Deepgram: a US company, EU endpoint.
        "stt_eu_provider": stt_provider() == "voxtral",
        "stt_eu_endpoint": True,
        "stt_training_opt_out": True,
        "clinical_decision_support": clinical_decision_support(),
        "econsult_nhg": econsult_nhg(),
    }


# ── Version of the extension that sent the request (for the logs and advice) ──
# Features such as the speech check in EU mode need a minimum version; the side
# panel warns when the installed extension is older.
MIN_EXTENSIE_VERSIE = "2.15.4"
_versie: ContextVar[str] = ContextVar("vitascribe_versie", default="")


def zet_versie(waarde: Optional[str]) -> Token:
    schoon = str(waarde or "").strip()[:20]
    return _versie.set(schoon if re.fullmatch(r"\d+(\.\d+){0,3}", schoon) else "")


def herstel_versie(token: Token) -> None:
    _versie.reset(token)


def versie() -> str:
    return _versie.get()


# ── Phase: internal use in the own practice, or distribution to others ──
# "intern" (default): VitaScribe is used only in the practice that runs it.
# No public sign-up; practices and users are added by the administrator.
# "extern": distribution to other practices (sign-up page open). Switching to
# extern is a deliberate step, after the agreements for distribution are in
# place (see docs/FASERING.md).
FASEN = ("intern", "extern")


def fase() -> str:
    gekozen = _env("VITASCRIBE_FASE", "intern").lower()
    return gekozen if gekozen in FASEN else "intern"
