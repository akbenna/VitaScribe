#!/bin/bash
# =============================================================================
# SmartVoice — Stop Alles (dubbelklik om te stoppen)
# =============================================================================
clear
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PROJECT_DIR="$HOME/Documents/GitHub/Smartvoice"
cd "$PROJECT_DIR" || exit 1

echo "========================================"
echo -e " ${RED}SmartVoice stoppen...${NC}"
echo "========================================"
echo ""

# Stop uvicorn (API)
echo -n "API server... "
pkill -f "uvicorn services.api.main:app" 2>/dev/null && echo -e "${GREEN}gestopt${NC}" || echo "draaide niet"

# Stop Next.js (frontend)
echo -n "Frontend... "
pkill -f "next dev" 2>/dev/null && echo -e "${GREEN}gestopt${NC}" || echo "draaide niet"

# Stop Docker containers
echo -n "Docker containers... "
docker compose -f docker-compose.dev.yml stop 2>/dev/null && echo -e "${GREEN}gestopt${NC}" || echo "draaide niet"

echo ""
echo "========================================"
echo -e " ${GREEN}SmartVoice is gestopt.${NC}"
echo "========================================"
echo ""
echo "Druk op een toets om te sluiten..."
read -n 1 -s
