#!/bin/bash
# =============================================================================
# VitaScribe - Systeemcheck vóór Opstarten
# =============================================================================
# Controleert of alle vereisten aanwezig zijn voor lokale deployment.
# Draai dit VOOR docker compose up.
#
# Gebruik: ./scripts/check_system.sh
# =============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
ERRORS=0

echo "========================================"
echo " VitaScribe Systeemcheck"
echo "========================================"
echo ""

# --- Docker ---
echo -n "[1/8] Docker... "
if command -v docker &>/dev/null; then
    DOCKER_V=$(docker --version 2>/dev/null | head -1)
    echo -e "${GREEN}OK${NC} ($DOCKER_V)"
else
    echo -e "${RED}NIET GEVONDEN${NC}"
    echo "      Installeer Docker: https://docs.docker.com/engine/install/"
    ERRORS=$((ERRORS+1))
fi

# --- Docker Compose ---
echo -n "[2/8] Docker Compose... "
if docker compose version &>/dev/null; then
    COMPOSE_V=$(docker compose version 2>/dev/null | head -1)
    echo -e "${GREEN}OK${NC} ($COMPOSE_V)"
else
    echo -e "${RED}NIET GEVONDEN${NC}"
    ERRORS=$((ERRORS+1))
fi

# --- NVIDIA GPU ---
echo -n "[3/8] NVIDIA GPU... "
if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
    echo -e "${GREEN}OK${NC} (${GPU_NAME}, ${GPU_MEM})"

    # VRAM check
    MEM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
    if [ -n "$MEM_MB" ] && [ "$MEM_MB" -lt 8000 ]; then
        echo -e "      ${YELLOW}WAARSCHUWING: <8GB VRAM - Whisper large-v3 + Llama 3.3 8B past krap${NC}"
        echo "      Aanbevolen: ≥12GB VRAM (RTX 3060 12GB, RTX 3090, RTX 4070+)"
    fi
else
    echo -e "${RED}NIET GEVONDEN${NC}"
    echo "      GPU is vereist voor Whisper STT en Ollama LLM."
    echo "      Installeer NVIDIA drivers + NVIDIA Container Toolkit."
    ERRORS=$((ERRORS+1))
fi

# --- NVIDIA Container Toolkit ---
echo -n "[4/8] NVIDIA Container Toolkit... "
if docker info 2>/dev/null | grep -q "nvidia"; then
    echo -e "${GREEN}OK${NC}"
elif command -v nvidia-container-cli &>/dev/null; then
    echo -e "${GREEN}OK${NC} (nvidia-container-cli gevonden)"
else
    echo -e "${YELLOW}ONZEKER${NC} - kan niet verifiëren"
    echo "      Als 'docker compose up' faalt met GPU errors:"
    echo "      https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
fi

# --- .env bestand ---
echo -n "[5/8] .env bestand... "
if [ -f ".env" ]; then
    echo -e "${GREEN}OK${NC}"
    # Check kritieke variabelen
    for VAR in "APP_SECRET_KEY" "POSTGRES_PASSWORD" "REDIS_PASSWORD"; do
        VAL=$(grep "^${VAR}=" .env 2>/dev/null | cut -d'=' -f2-)
        if [ -z "$VAL" ] || [ "$VAL" = "CHANGE_ME" ] || [ "$VAL" = "CHANGE_ME_GENERATE_WITH_openssl_rand_hex_32" ]; then
            echo -e "      ${YELLOW}WAARSCHUWING: ${VAR} moet nog ingesteld worden${NC}"
        fi
    done
else
    echo -e "${RED}NIET GEVONDEN${NC}"
    echo "      Kopieer: cp .env.example .env && pas waarden aan"
    ERRORS=$((ERRORS+1))
fi

# --- Poorten ---
echo -n "[6/8] Poorten beschikbaar... "
PORTS_OK=true
for PORT in 5432 6379 8000 11434; do
    if ss -tlnp 2>/dev/null | grep -q ":${PORT} " || netstat -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        echo -e "\n      ${YELLOW}Poort ${PORT} is al in gebruik${NC}"
        PORTS_OK=false
    fi
done
if [ "$PORTS_OK" = true ]; then
    echo -e "${GREEN}OK${NC} (5432, 6379, 8000, 11434 vrij)"
fi

# --- Schijfruimte ---
echo -n "[7/8] Schijfruimte... "
FREE_GB=$(df -BG . 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
if [ -n "$FREE_GB" ] && [ "$FREE_GB" -gt 20 ]; then
    echo -e "${GREEN}OK${NC} (${FREE_GB}GB beschikbaar)"
elif [ -n "$FREE_GB" ]; then
    echo -e "${YELLOW}WEINIG${NC} (${FREE_GB}GB - aanbevolen ≥20GB)"
    echo "      Whisper model (~3GB) + Ollama model (~5GB) + Docker images"
else
    echo -e "${YELLOW}ONZEKER${NC}"
fi

# --- HuggingFace token (voor PyAnnote diarisatie) ---
echo -n "[8/8] HuggingFace token... "
if [ -f ".env" ]; then
    HF=$(grep "^HF_TOKEN=" .env 2>/dev/null | cut -d'=' -f2-)
    if [ -n "$HF" ] && [ "$HF" != "CHANGE_ME" ]; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}ONTBREEKT${NC} - diarisatie (arts/patient herkenning) werkt niet"
        echo "      Maak een token aan op https://huggingface.co/settings/tokens"
        echo "      Accepteer de PyAnnote licentie op https://huggingface.co/pyannote/speaker-diarization-3.1"
    fi
else
    echo -e "${YELLOW}OVERGESLAGEN${NC} (.env ontbreekt)"
fi

echo ""
echo "========================================"
if [ $ERRORS -gt 0 ]; then
    echo -e " ${RED}${ERRORS} PROBLEMEN GEVONDEN - fix deze eerst${NC}"
else
    echo -e " ${GREEN}ALLES OK - klaar voor: docker compose up -d${NC}"
fi
echo "========================================"
echo ""
echo "Volgende stappen:"
echo "  1. docker compose up -d postgres redis ollama"
echo "  2. docker compose exec ollama ollama pull llama3.1:8b"
echo "  3. docker compose up -d"
echo "  4. ./scripts/test_e2e.sh"
