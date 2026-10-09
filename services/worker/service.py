"""
Pipeline Worker
===============
Haalt verwerkingsjobs uit de Redis Stream en draait de pipeline.

Architectuur:
  - API ontvangt audio-upload → plaatst job in Redis Stream "jobs:pipeline"
  - Worker(s) luisteren op de stream → verwerken één consult per keer
  - Meerdere workers kunnen parallel draaien (consumer group)
  - Elke worker claimt precies één job tegelijk (geen dubbel werk)

Schalen:
  docker compose up --scale worker=3  # 3 parallelle workers
  OF: meerdere GPU-servers met elk hun eigen worker-containers

CPU vs GPU:
  Worker detecteert automatisch of CUDA beschikbaar is.
  Zonder GPU: Whisper small/medium + int8, langzamer maar functioneel.
"""

import asyncio
import json
import os
import signal
import uuid
from datetime import datetime, timezone

import structlog

# Pad setup
import sys
from pathlib import Path
_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from shared.config.settings import config
from shared.database import init_db, close_db, async_session
from shared.redis_client import redis_client
from services.pipeline.orchestrator import PipelineOrchestrator

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------
STREAM_NAME = "jobs:pipeline"
CONSUMER_GROUP = "pipeline-workers"
CONSUMER_NAME = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
BLOCK_MS = 5000           # Wacht max 5s op nieuwe jobs
CLAIM_TIMEOUT_MS = 300000  # Hercliam jobs die >5 min pending zijn (crashed worker)
MAX_RETRIES = 3


class PipelineWorker:
    """
    Verwerkt consultatie-audio via de pipeline.
    Draait als standalone process, schaalt horizontaal.
    """

    def __init__(self):
        self.pipeline = PipelineOrchestrator()
        self._running = False
        self._jobs_processed = 0

    async def start(self):
        """Start de worker loop."""
        self._running = True
        logger.info(
            "Worker gestart",
            consumer=CONSUMER_NAME,
            stream=STREAM_NAME,
            group=CONSUMER_GROUP,
        )

        # Database + Redis verbinding
        await init_db()
        await redis_client.connect()

        # Maak consumer group aan (idempotent)
        try:
            await redis_client.client.xgroup_create(
                STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True
            )
            logger.info("Consumer group aangemaakt", group=CONSUMER_GROUP)
        except Exception:
            # Groep bestaat al - prima
            pass

        # Laad ML-modellen
        logger.info("ML-modellen laden...")
        await self.pipeline.initialize()
        logger.info("Worker klaar voor jobs")

        # Verwerk eerst eventuele onafgemaakte jobs (na crash/restart)
        await self._reclaim_pending_jobs()

        # Hoofdloop
        while self._running:
            try:
                await self._process_next_job()
            except Exception as e:
                logger.error("Worker loop fout", error=str(e))
                await asyncio.sleep(2)

        # Cleanup
        await close_db()
        await redis_client.disconnect()
        logger.info(
            "Worker gestopt",
            consumer=CONSUMER_NAME,
            jobs_verwerkt=self._jobs_processed,
        )

    async def stop(self):
        """Stop de worker gracefully."""
        logger.info("Worker wordt gestopt...", consumer=CONSUMER_NAME)
        self._running = False

    async def _process_next_job(self):
        """Haal de volgende job uit de stream en verwerk."""
        try:
            # Lees één job uit de stream (blocking)
            messages = await redis_client.client.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_NAME: ">"},
                count=1,
                block=BLOCK_MS,
            )
        except Exception as e:
            logger.warning("Redis read fout", error=str(e))
            await asyncio.sleep(1)
            return

        if not messages:
            return  # Geen nieuwe jobs

        # Parse job
        for stream_name, entries in messages:
            for message_id, data in entries:
                await self._handle_job(message_id, data)

    async def _handle_job(self, message_id: str, data: dict):
        """Verwerk één pipeline job."""
        consult_id = data.get("consult_id", "")
        audio_path = data.get("audio_path", "")
        retry_count = int(data.get("retry_count", "0"))

        logger.info(
            "Job ontvangen",
            consumer=CONSUMER_NAME,
            consult_id=consult_id,
            audio_path=audio_path,
            message_id=message_id,
        )

        try:
            async with async_session() as db:
                await self.pipeline.process_consult(
                    db, uuid.UUID(consult_id), audio_path
                )

            # Job succesvol - acknowledge
            await redis_client.client.xack(
                STREAM_NAME, CONSUMER_GROUP, message_id
            )
            self._jobs_processed += 1

            logger.info(
                "Job voltooid",
                consumer=CONSUMER_NAME,
                consult_id=consult_id,
                totaal_verwerkt=self._jobs_processed,
            )

        except Exception as e:
            logger.error(
                "Job mislukt",
                consumer=CONSUMER_NAME,
                consult_id=consult_id,
                error=str(e),
                retry=retry_count,
            )

            # Acknowledge de gefaalde job (anders blockeert ie de queue)
            await redis_client.client.xack(
                STREAM_NAME, CONSUMER_GROUP, message_id
            )

            # Retry indien onder max
            if retry_count < MAX_RETRIES:
                logger.info(
                    "Job opnieuw in queue",
                    consult_id=consult_id,
                    retry=retry_count + 1,
                )
                await redis_client.client.xadd(
                    STREAM_NAME,
                    {
                        "consult_id": consult_id,
                        "audio_path": audio_path,
                        "retry_count": str(retry_count + 1),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            else:
                logger.error(
                    "Job definitief mislukt na max retries",
                    consult_id=consult_id,
                    max_retries=MAX_RETRIES,
                )

    async def _reclaim_pending_jobs(self):
        """Hercliam jobs van gecrashte workers (pending > timeout)."""
        try:
            pending = await redis_client.client.xpending_range(
                STREAM_NAME,
                CONSUMER_GROUP,
                min="-",
                max="+",
                count=100,
            )

            for entry in pending:
                # entry: {'message_id': ..., 'consumer': ..., 'time_since_delivered': ..., 'times_delivered': ...}
                idle_ms = entry.get("time_since_delivered", 0)
                if idle_ms > CLAIM_TIMEOUT_MS:
                    msg_id = entry["message_id"]
                    claimed = await redis_client.client.xclaim(
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        min_idle_time=CLAIM_TIMEOUT_MS,
                        message_ids=[msg_id],
                    )
                    if claimed:
                        logger.info(
                            "Pending job herclaimd",
                            consumer=CONSUMER_NAME,
                            message_id=msg_id,
                        )

        except Exception as e:
            logger.warning("Pending jobs check mislukt", error=str(e))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
async def main():
    worker = PipelineWorker()

    # Graceful shutdown via SIGTERM/SIGINT
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))

    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
