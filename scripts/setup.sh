#!/usr/bin/env bash
# =============================================================================
# AI-Consultassistent - Setup Script
# =============================================================================
# Gebruik: bash scripts/setup.sh
# Vereist: Ubuntu 24.04, NVIDIA GPU, Docker
# =============================================================================

set -euo pipefail

echo "============================================"
echo " AI-Consultassistent - Setup"
echo "============================================"

# --- Checks ---
echo ""
echo "[1/7] Systeemchecks..."

if ! command -v docker &> /dev/null; then
    echo "  X Docker niet gevonden. Installeer: https://docs.docker.com/engine/install/"
    exit 1
fi
echo "  V Docker gevonden"

if ! command -v nvidia-smi &> /dev/null; then
    echo "  ! NVIDIA driver niet gevonden. GPU-verwerking niet beschikbaar."
    echo "    Installeer: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
else
    echo "  V NVIDIA GPU gevonden: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
fi

# --- Environment ---
echo ""
echo "[2/7] Environment configuratie..."

if [ ! -f .env ]; then
    cp .env.example .env
    # Genereer random keys
    SECRET_KEY=$(openssl rand -hex 32)
    DB_KEY=$(openssl rand -hex 32)
    REDIS_PASS=$(openssl rand -hex 16)
    DB_PASS=$(openssl rand -hex 16)

    sed -i "s/APP_SECRET_KEY=CHANGE_ME.*/APP_SECRET_KEY=$SECRET_KEY/" .env
    sed -i "s/DB_ENCRYPTION_KEY=CHANGE_ME.*/DB_ENCRYPTION_KEY=$DB_KEY/" .env
    sed -i "s/REDIS_PASSWORD=CHANGE_ME/REDIS_PASSWORD=$REDIS_PASS/" .env
    sed -i "s/POSTGRES_PASSWORD=CHANGE_ME/POSTGRES_PASSWORD=$DB_PASS/" .env

    echo "  V .env aangemaakt met gegenereerde sleutels"
    echo "  ! Controleer .env en pas HF_TOKEN aan voor diarisatie"
else
    echo "  V .env bestaat al"
fi

# --- Ollama ---
echo ""
echo "[3/7] Ollama installatie..."

if ! command -v ollama &> /dev/null; then
    echo "  Installeer Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "  V Ollama geinstalleerd"
else
    echo "  V Ollama al aanwezig"
fi

echo "  Model downloaden (dit kan even duren)..."
ollama pull llama3.1:8b || {
    echo "  ! Model pull mislukt. Probeer handmatig: ollama pull llama3.1:8b"
}

# --- Data directories ---
echo ""
echo "[4/7] Data directories aanmaken..."

mkdir -p data/{audio,audit,models,backups}
chmod 700 data/audio data/audit
echo "  V Directories aangemaakt"

# --- Docker build ---
echo ""
echo "[5/7] Docker images bouwen..."

docker compose build
echo "  V Images gebouwd"

# --- Database ---
echo ""
echo "[6/7] Database initialiseren..."

docker compose up -d postgres
echo "  Wacht op PostgreSQL..."
sleep 5
docker compose exec postgres pg_isready -U ca_app -d consultassistent || {
    echo "  Wacht nog even..."
    sleep 10
}
echo "  V Database gereed (migratie wordt automatisch uitgevoerd)"

# --- Start ---
echo ""
echo "[7/7] Services starten..."

docker compose up -d
echo "  V Alle services gestart"

echo ""
echo "============================================"
echo " Setup voltooid!"
echo "============================================"
echo ""
echo " Frontend:  http://localhost:3000"
echo " API:       http://localhost:8000"
echo " API docs:  http://localhost:8000/docs"
echo ""
echo " Volgende stappen:"
echo "  1. Controleer .env configuratie"
echo "  2. Stel HF_TOKEN in voor diarisatie"
echo "  3. Test met: curl http://localhost:8000/health"
echo "  4. Open http://localhost:3000 in je browser"
echo ""
