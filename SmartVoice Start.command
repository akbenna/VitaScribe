#!/bin/bash
# =============================================================================
# SmartVoice — Start Alles (dubbelklik om te starten)
# =============================================================================
clear
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$HOME/Documents/GitHub/Smartvoice"
cd "$PROJECT_DIR" || { echo "Project niet gevonden op $PROJECT_DIR"; exit 1; }

echo "========================================"
echo -e " ${GREEN}SmartVoice AI-Consultassistent${NC}"
echo " Alles wordt gestart..."
echo "========================================"
echo ""

# --- 1. Ollama ---
echo -n "[1/5] Ollama... "
if pgrep -x "ollama" >/dev/null || curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "${GREEN}draait al${NC}"
else
    echo -e "${YELLOW}starten...${NC}"
    open -a Ollama 2>/dev/null || ollama serve &>/dev/null &
    sleep 3
fi

# --- 2. Docker ---
echo -n "[2/5] Docker Desktop... "
if docker info &>/dev/null 2>&1; then
    echo -e "${GREEN}draait al${NC}"
else
    echo -e "${YELLOW}starten...${NC}"
    open -a Docker
    echo -n "      Wachten op Docker"
    for i in {1..60}; do
        if docker info &>/dev/null 2>&1; then
            echo -e " ${GREEN}OK${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done
fi

# --- 3. PostgreSQL + Redis ---
echo -n "[3/5] Database + Redis... "
# Check of containers al draaien
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "ca-postgres"; then
    echo -e "${GREEN}draait al${NC}"
else
    docker compose -f docker-compose.dev.yml up -d postgres redis 2>/dev/null
    sleep 2
    echo -e "${GREEN}gestart${NC}"
fi

# --- 4. Backend API ---
echo -n "[4/5] Backend API (poort 8001)... "
if curl -s http://localhost:8001/health >/dev/null 2>&1; then
    echo -e "${GREEN}draait al${NC}"
else
    source venv/bin/activate 2>/dev/null
    echo -e "${YELLOW}starten...${NC}"
    # Start in achtergrond, log naar bestand
    nohup bash -c "cd $PROJECT_DIR && source venv/bin/activate && uvicorn services.api.main:app --port 8001 2>&1" > /tmp/smartvoice-api.log 2>&1 &
    API_PID=$!
    # Wacht tot API klaar is
    for i in {1..30}; do
        if curl -s http://localhost:8001/health >/dev/null 2>&1; then
            echo -e "      ${GREEN}OK${NC} (PID: $API_PID)"
            break
        fi
        sleep 1
    done
fi

# --- 5. Frontend ---
echo -n "[5/5] Frontend (poort 3000)... "
if curl -s http://localhost:3000 >/dev/null 2>&1; then
    echo -e "${GREEN}draait al${NC}"
else
    echo -e "${YELLOW}starten...${NC}"
    nohup bash -c "cd $PROJECT_DIR/frontend/review-app && NEXT_PUBLIC_API_URL=http://localhost:8001 npx next dev 2>&1" > /tmp/smartvoice-frontend.log 2>&1 &
    FE_PID=$!
    for i in {1..20}; do
        if curl -s http://localhost:3000 >/dev/null 2>&1; then
            echo -e "      ${GREEN}OK${NC} (PID: $FE_PID)"
            break
        fi
        sleep 1
    done
fi

echo ""
echo "========================================"
echo -e " ${GREEN}SmartVoice is klaar!${NC}"
echo "========================================"
echo ""
echo " Frontend:  http://localhost:3000"
echo " API:       http://localhost:8001"
echo " Health:    http://localhost:8001/health"
echo ""
echo " Login: arts1 / arts123"
echo ""
echo " Logs:"
echo "   API:      tail -f /tmp/smartvoice-api.log"
echo "   Frontend: tail -f /tmp/smartvoice-frontend.log"
echo ""

# Open browser
sleep 2
open "http://localhost:3000"

echo "Druk op een toets om dit venster te sluiten..."
read -n 1 -s
