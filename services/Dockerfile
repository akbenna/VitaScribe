# =============================================================================
# AI-Consultassistent - Backend Services (Lokale GPU)
# =============================================================================
# Multi-stage build: Python 3.12 + CUDA runtime voor Whisper/PyAnnote
# Build context: project root (niet services/)
#
# Bevat: FastAPI + Whisper STT + PyAnnote diarisatie + Ollama client
# Ollama zelf draait als aparte container (zie docker-compose.yml)
# =============================================================================

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS base

# Systeemafhankelijkheden + Python 3.12 via deadsnakes PPA
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python setup
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# PyTorch met CUDA 12.4 - apart installeren voor correcte GPU build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu124

# Overige dependencies (Whisper, PyAnnote, FastAPI, etc.)
COPY services/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Applicatie
WORKDIR /app
COPY services/ /app/services/
COPY shared/ /app/shared/
COPY database/ /app/database/
COPY scripts/ /app/scripts/

# Shared modules beschikbaar maken
ENV PYTHONPATH="/app"

RUN chmod +x /app/scripts/railway_start.sh || true

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Start: database init + seed (optioneel) + uvicorn
# Workers=1 omdat Whisper/PyAnnote GPU memory deelt met Ollama
CMD ["/bin/bash", "-c", "\
    python -c 'import asyncio; from shared.database import init_db, engine; asyncio.run(init_db()); asyncio.run(engine.dispose())' && \
    if [ \"${SEED_ON_START}\" = 'true' ]; then python /app/scripts/seed_production.py; fi && \
    uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info \
"]
