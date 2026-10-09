#!/usr/bin/env bash
# =============================================================================
# VitaScribe - Zelflerende jobs (Fase 2)
# =============================================================================
# Draait beide leerjobs achter elkaar:
#   1. Vocabulaire-job  (niveau 1): leert woordenlijstcorrecties uit feedback
#   2. Few-shot-bank    (niveau 2): vult voorbeeldbank uit goedgekeurde SOEP's
#
# Bedoeld om periodiek te draaien via systemd-timer of cron (zie
# docs/ZELFLEREND_SCHEDULING.md). Volledig lokaal; verwerkt geen data buiten
# de praktijk.
#
# Gebruik:
#   scripts/run_learning_jobs.sh
#
# Omgevingsvariabelen (optioneel):
#   VITASCRIBE_ROOT   projectroot (default: map boven dit script)
#   PYTHON_BIN        python-interpreter (default: .venv/bin/python of python3)
#   LEARNING_LOG_DIR  logmap (default: $VITASCRIBE_ROOT/logs)
# =============================================================================

set -euo pipefail

# --- Projectroot bepalen ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# SMARTVOICE_ROOT is de naam van voor de overstap naar VitaScribe; een server
# die hem nog zet blijft werken tot de omgeving is bijgewerkt.
VITASCRIBE_ROOT="${VITASCRIBE_ROOT:-${SMARTVOICE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}}"
cd "$VITASCRIBE_ROOT"

# --- Python-interpreter kiezen (venv heeft voorkeur) ---
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$VITASCRIBE_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$VITASCRIBE_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || command -v python)"
  fi
fi

# --- .env laden indien aanwezig (DB-, pad- en drempelinstellingen) ---
if [[ -f "$VITASCRIBE_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$VITASCRIBE_ROOT/.env"
  set +a
fi

export PYTHONPATH="$VITASCRIBE_ROOT:${PYTHONPATH:-}"

# --- Logging ---
LEARNING_LOG_DIR="${LEARNING_LOG_DIR:-$VITASCRIBE_ROOT/logs}"
mkdir -p "$LEARNING_LOG_DIR"
LOG_FILE="$LEARNING_LOG_DIR/learning_$(date +%Y%m%d_%H%M%S).log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "Start zelflerende jobs (root=$VITASCRIBE_ROOT, python=$PYTHON_BIN)"

status=0

log "── Job 1/2: vocabulaire-leren ──"
if "$PYTHON_BIN" tools/learn_vocabulary.py >>"$LOG_FILE" 2>&1; then
  log "Vocabulaire-job OK"
else
  status=1
  log "Vocabulaire-job MISLUKT (zie log)"
fi

log "── Job 2/2: few-shot-bank bouwen ──"
if "$PYTHON_BIN" tools/build_fewshot_bank.py >>"$LOG_FILE" 2>&1; then
  log "Few-shot-job OK"
else
  status=1
  log "Few-shot-job MISLUKT (zie log)"
fi

log "Klaar (exit=$status)"
exit "$status"
