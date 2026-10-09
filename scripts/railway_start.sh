#!/bin/bash
# =============================================================================
# Railway Start Script - Database initialisatie + API server
# =============================================================================
set -e

echo "[railway] Starting AI-Consultassistent..."
echo "[railway] APP_ENV=${APP_ENV:-development}"
echo "[railway] PORT=${PORT:-8000}"

# 1. Database migratie/init
echo "[railway] Initializing database..."
python -c "
import asyncio, sys
sys.path.insert(0, '/app')
from shared.database import init_db, engine
async def run():
    await init_db()
    await engine.dispose()
    print('[railway] Database initialized.')
asyncio.run(run())
"

# 2. Seed gebruikers als SEED_ON_START=true
if [ "${SEED_ON_START}" = "true" ]; then
    echo "[railway] Seeding initial users..."
    python /app/scripts/seed_production.py
fi

# 3. Start uvicorn
echo "[railway] Starting uvicorn on port ${PORT:-8000}..."
exec uvicorn services.api.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 2 \
    --log-level warning
