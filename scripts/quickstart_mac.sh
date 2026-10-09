#!/bin/bash
# =============================================================================
# VitaScribe - Quickstart voor macOS (Development)
# =============================================================================
# Dit script:
#   1. Checkt of Ollama geïnstalleerd is
#   2. Start PostgreSQL + Redis via Docker
#   3. Kopieert .env.dev naar .env
#   4. Installeert Python dependencies
#   5. Seeded de database met test-users
#   6. Start de API server
#
# Vereisten:
#   - Docker Desktop for Mac (draaiend)
#   - Python 3.12+
#   - Ollama (ollama.com/download)
# =============================================================================
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$(dirname "$0")/.."
echo "========================================"
echo " VitaScribe - macOS Quickstart"
echo " $(pwd)"
echo "========================================"
echo ""

# --- 0. Python 3.12 ---
echo -n "[0/7] Python 3.12... "
PYTHON_CMD=""
if command -v python3.12 &>/dev/null; then
    PYTHON_CMD="python3.12"
    echo -e "${GREEN}OK${NC} ($(python3.12 --version))"
elif python3 --version 2>/dev/null | grep -q "3.1[2-9]"; then
    PYTHON_CMD="python3"
    echo -e "${GREEN}OK${NC} ($(python3 --version))"
else
    PY_VERSION=$(python3 --version 2>/dev/null || echo "niet gevonden")
    echo -e "${RED}NIET GEVONDEN${NC} (huidig: ${PY_VERSION})"
    echo ""
    echo "  De code vereist Python 3.12+. Installeer:"
    echo "    brew install python@3.12"
    echo ""
    echo "  Start daarna opnieuw: ./scripts/quickstart_mac.sh"
    exit 1
fi
echo ""

# --- 1. Ollama ---
echo -n "[1/7] Ollama... "
if command -v ollama &>/dev/null; then
    echo -e "${GREEN}OK${NC}"
    # Check of model al gepulled is
    if ollama list 2>/dev/null | grep -q "llama3.1:8b"; then
        echo -e "      Model llama3.1 ${GREEN}aanwezig${NC}"
    else
        echo -e "      ${YELLOW}Model niet gevonden - nu pullen...${NC}"
        echo "      Dit duurt ~5 minuten (download ~4.7GB)"
        ollama pull llama3.1:8b
    fi
else
    echo -e "${RED}NIET GEVONDEN${NC}"
    echo ""
    echo "  Installeer Ollama:"
    echo "    brew install ollama"
    echo "    of download van: https://ollama.com/download"
    echo ""
    echo "  Start Ollama daarna:"
    echo "    ollama serve"
    echo ""
    exit 1
fi
echo ""

# --- 2. Docker ---
echo -n "[2/7] Docker Desktop... "
if docker info &>/dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}NIET DRAAIEND${NC}"
    echo "      Start Docker Desktop en probeer opnieuw."
    exit 1
fi
echo ""

# --- 3. PostgreSQL + Redis ---
echo "[3/7] Database + Redis starten..."
# Stop en verwijder oude containers + volumes (schone start)
docker compose -f docker-compose.dev.yml down -v 2>/dev/null || true
docker compose -f docker-compose.dev.yml up -d postgres redis
echo -e "      ${GREEN}OK${NC}"
echo ""

# --- 4. .env ---
echo -n "[4/7] Environment configuratie... "
if [ ! -f ".env" ]; then
    cp .env.dev .env
    echo -e "${GREEN}OK${NC} (.env.dev gekopieerd naar .env)"
else
    echo -e "${GREEN}OK${NC} (.env bestaat al)"
fi
echo ""

# --- 5. Python dependencies ---
echo "[5/7] Python dependencies installeren..."
if [ ! -d "venv" ] || ! venv/bin/python --version 2>/dev/null | grep -q "3.1[2-9]"; then
    rm -rf venv
    $PYTHON_CMD -m venv venv
    echo "      Virtuele omgeving aangemaakt ($PYTHON_CMD)"
fi
source venv/bin/activate

# Mac-specifieke dependencies (geen CUDA torch, geen PyAnnote)
pip install --quiet --upgrade pip
pip install --quiet -r services/requirements-mac.txt 2>&1 | tail -5
echo -e "      ${GREEN}OK${NC}"
echo ""

# --- 6. Database seeden ---
echo "[6/7] Database initialiseren en seeden..."
# Wacht tot PostgreSQL klaar is
echo -n "      Wachten op PostgreSQL... "
for i in {1..30}; do
    if docker compose -f docker-compose.dev.yml exec -T postgres pg_isready -U ca_app -d consultassistent &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        break
    fi
    sleep 1
done

export SEED_ON_START=true
export ADMIN_PASSWORD=admin123
export ARTS_PASSWORD=arts123
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from shared.database import init_db, engine
async def run():
    await init_db()
    await engine.dispose()
asyncio.run(run())
" 2>&1 | grep -v "UserWarning"
python scripts/seed_production.py 2>&1 | grep -v "UserWarning"
echo ""

# --- 7. Start API ---
echo "========================================"
echo -e " ${GREEN}KLAAR!${NC}"
echo "========================================"
echo ""
echo " Ollama draait op:     http://localhost:11434"
echo " PostgreSQL draait op: localhost:${POSTGRES_PORT:-5433}"
echo " Redis draait op:      localhost:${REDIS_PORT:-6380}"
echo ""
echo " Test-accounts:"
echo "   admin / admin123  (beheerder)"
echo "   arts1 / arts123   (arts)"
echo ""
echo " Start de API server:"
echo "   source venv/bin/activate"
echo "   uvicorn services.api.main:app --reload --port 8000"
echo ""
echo " Start de frontend (in een andere terminal):"
echo "   cd frontend/review-app && npm run dev"
echo ""
echo " Test de pipeline:"
echo "   ./scripts/test_e2e.sh"
echo ""
