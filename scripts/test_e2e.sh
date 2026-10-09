#!/bin/bash
# =============================================================================
# VitaScribe - End-to-End Test
# =============================================================================
# Test de volledige pipeline: upload audio → transcriptie → SOEP
#
# Gebruik:
#   ./scripts/test_e2e.sh                          # standaard localhost:8000
#   ./scripts/test_e2e.sh https://jouw-api.up.railway.app
# =============================================================================
set -e

API_URL="${1:-http://localhost:8000}"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo " VitaScribe E2E Test"
echo " API: ${API_URL}"
echo "========================================"
echo ""

# --- Stap 0: Health check ---
echo -n "[1/7] Health check... "
HEALTH=$(curl -s "${API_URL}/health")
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
if [ "$STATUS" = "ok" ] || [ "$STATUS" = "degraded" ]; then
    echo -e "${GREEN}OK${NC} (status: ${STATUS})"
    echo "      Services: $(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin)['services']; print(', '.join(f'{k}={v}' for k,v in d.items()))")"
else
    echo -e "${RED}FAILED${NC}"
    echo "      Response: $HEALTH"
    exit 1
fi
echo ""

# --- Stap 1: Ollama check ---
echo -n "[2/7] Ollama beschikbaar... "
OLLAMA_STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin)['services'].get('ollama','unchecked'))" 2>/dev/null || echo "error")
if [ "$OLLAMA_STATUS" = "ok" ]; then
    echo -e "${GREEN}OK${NC}"
elif [ "$OLLAMA_STATUS" = "model_missing" ]; then
    echo -e "${YELLOW}WAARSCHUWING: model niet gevonden${NC}"
    echo "      Probeer: docker compose exec ollama ollama pull llama3.1:8b"
else
    echo -e "${RED}NIET BESCHIKBAAR (${OLLAMA_STATUS})${NC}"
    echo "      Ollama moet draaien voor de pipeline."
fi
echo ""

# --- Stap 2: Login ---
echo -n "[3/7] Login als arts1... "
LOGIN_RESP=$(curl -s -X POST "${API_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"arts1","password":"changeme123!"}')

TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
if [ -n "$TOKEN" ] && [ "$TOKEN" != "" ]; then
    echo -e "${GREEN}OK${NC} (token ontvangen)"
else
    echo -e "${YELLOW}GEEN TOKEN${NC} - probeer met ADMIN_PASSWORD env var"
    echo "      Response: $LOGIN_RESP"
    TOKEN=""
fi
echo ""

# --- Stap 3: Maak test audio ---
echo -n "[4/7] Test audio genereren... "
TEST_AUDIO="/tmp/vitascribe_test.wav"
# Genereer 3 seconden stilte als WAV (voor pipeline test)
python3 -c "
import struct, wave
with wave.open('${TEST_AUDIO}', 'w') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    # 3 seconden stilte
    w.writeframes(b'\x00\x00' * 48000)
print('OK')
" 2>/dev/null || ffmpeg -f lavfi -i "sine=frequency=440:duration=3" -ar 16000 -ac 1 "${TEST_AUDIO}" -y -loglevel quiet 2>/dev/null
if [ -f "$TEST_AUDIO" ]; then
    echo -e "${GREEN}OK${NC} (${TEST_AUDIO})"
else
    echo -e "${RED}FAILED${NC} - kan geen test audio maken"
    exit 1
fi
echo ""

# --- Stap 4: Upload audio ---
echo -n "[5/7] Audio uploaden... "
UPLOAD_RESP=$(curl -s -X POST "${API_URL}/api/consult/upload" \
    -F "file=@${TEST_AUDIO};filename=test_consult.wav" \
    -F "patient_hash=test_sha256_hash")

SESSION_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")
if [ -n "$SESSION_ID" ] && [ "$SESSION_ID" != "" ]; then
    echo -e "${GREEN}OK${NC} (session: ${SESSION_ID})"
else
    echo -e "${RED}FAILED${NC}"
    echo "      Response: $UPLOAD_RESP"
    exit 1
fi
echo ""

# --- Stap 5: Poll status ---
echo "[6/7] Pipeline status pollen..."
MAX_POLLS=60
POLL_INTERVAL=5
for i in $(seq 1 $MAX_POLLS); do
    STATUS_RESP=$(curl -s "${API_URL}/api/consult/${SESSION_ID}/status")
    CURRENT=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

    # Stappen
    STEPS=$(echo "$STATUS_RESP" | python3 -c "
import sys,json
d=json.load(sys.stdin).get('steps',{})
print(' | '.join(f'{k}:{v}' for k,v in d.items()))
" 2>/dev/null || echo "?")

    echo "      [${i}/${MAX_POLLS}] Status: ${CURRENT} - ${STEPS}"

    if [ "$CURRENT" = "reviewing" ] || [ "$CURRENT" = "approved" ] || [ "$CURRENT" = "exported" ]; then
        echo -e "      ${GREEN}Pipeline voltooid!${NC}"
        break
    elif [ "$CURRENT" = "failed" ]; then
        echo -e "      ${RED}Pipeline mislukt${NC}"
        break
    fi

    sleep $POLL_INTERVAL
done
echo ""

# --- Stap 6: Haal SOEP op ---
echo -n "[7/7] SOEP concept ophalen... "
if [ "$CURRENT" = "reviewing" ] || [ "$CURRENT" = "approved" ]; then
    SOEP_RESP=$(curl -s "${API_URL}/api/consult/${SESSION_ID}/soep")
    echo -e "${GREEN}OK${NC}"
    echo ""
    echo "========================================"
    echo " SOEP RESULTAAT"
    echo "========================================"
    echo "$SOEP_RESP" | python3 -m json.tool 2>/dev/null || echo "$SOEP_RESP"
    echo ""

    # Detectie
    DET_RESP=$(curl -s "${API_URL}/api/consult/${SESSION_ID}/detection")
    echo "========================================"
    echo " DETECTIE (rode vlaggen + ontbrekend)"
    echo "========================================"
    echo "$DET_RESP" | python3 -m json.tool 2>/dev/null || echo "$DET_RESP"
else
    echo -e "${YELLOW}OVERGESLAGEN${NC} - pipeline niet afgerond (status: ${CURRENT})"
fi

echo ""
echo "========================================"
echo " Test voltooid"
echo "========================================"

# Cleanup
rm -f "${TEST_AUDIO}"
