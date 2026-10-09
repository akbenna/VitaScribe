#!/bin/bash
# =============================================================================
# VitaScribe - Stop Alles (dubbelklik om te stoppen)
# =============================================================================
clear
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Het project zoeken in plaats van één vaste map aan te nemen. Eerst de map waar
# dit script zelf staat (ook als je het via een alias of het Dock opent), dan de
# gebruikelijke plekken onder de nieuwe en de oude naam. Zo blijft dubbelklikken
# werken, of de map nu VitaScribe of nog Smartvoice heet.
PROJECT_DIR=""
for kandidaat in "$(cd "$(dirname "$0")" && pwd)" \
                 "$HOME/Documents/GitHub/VitaScribe" \
                 "$HOME/Documents/GitHub/Smartvoice"; do
  if [ -f "$kandidaat/chrome-extension/manifest.json" ]; then PROJECT_DIR="$kandidaat"; break; fi
done
if [ -z "$PROJECT_DIR" ] || ! cd "$PROJECT_DIR"; then echo "Project niet gevonden."; exit 1; fi

echo "========================================"
echo -e " ${RED}VitaScribe stoppen...${NC}"
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
echo -e " ${GREEN}VitaScribe is gestopt.${NC}"
echo "========================================"
echo ""
echo "Druk op een toets om te sluiten..."
read -n 1 -s
