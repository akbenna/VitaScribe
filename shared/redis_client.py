"""
Redis Client - Event bus en status caching.

Gebruik:
    from shared.redis_client import redis_client

    # Status update publiceren
    await redis_client.publish_status(consult_id, "transcribing")

    # Status ophalen
    status = await redis_client.get_status(consult_id)
"""

import json

import redis.asyncio as redis
import structlog

from shared.config.settings import config

logger = structlog.get_logger()


class RedisClient:
    """Async Redis client voor event bus en caching."""

    def __init__(self):
        self._client: redis.Redis | None = None

    async def connect(self):
        """Maak verbinding met Redis."""
        self._client = redis.from_url(
            config.redis.url,
            decode_responses=True,
        )
        await self._client.ping()
        logger.info("Redis connectie OK")

    async def disconnect(self):
        """Sluit de Redis connectie."""
        if self._client:
            await self._client.close()

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis niet verbonden. Roep connect() aan.")
        return self._client

    # --- Status Caching ---

    async def set_status(self, consult_id: str, status: str, details: dict | None = None):
        """Cache de verwerkingsstatus van een consult."""
        data = {"status": status, **(details or {})}
        await self.client.setex(
            f"consult:{consult_id}:status",
            300,  # 5 minuten TTL
            json.dumps(data),
        )

    async def get_status(self, consult_id: str) -> dict | None:
        """Haal gecachte status op."""
        data = await self.client.get(f"consult:{consult_id}:status")
        if data:
            return json.loads(data)
        return None

    # --- Event Bus (Pub/Sub) ---

    async def publish_event(self, channel: str, event: dict):
        """Publiceer een event op een kanaal."""
        await self.client.publish(channel, json.dumps(event))
        logger.debug("Event gepubliceerd", channel=channel)

    async def publish_status(self, consult_id: str, status: str, step: str = ""):
        """Publiceer een status-update event."""
        await self.set_status(consult_id, status, {"step": step})
        await self.publish_event("pipeline:status", {
            "consult_id": consult_id,
            "status": status,
            "step": step,
        })

    # --- Stream (voor betrouwbare berichten) ---

    async def add_to_stream(self, stream: str, data: dict):
        """Voeg een bericht toe aan een Redis Stream."""
        await self.client.xadd(stream, {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()})

    async def read_stream(self, stream: str, last_id: str = "0", count: int = 10) -> list:
        """Lees berichten uit een Redis Stream."""
        messages = await self.client.xread({stream: last_id}, count=count, block=1000)
        return messages


# Singleton
redis_client = RedisClient()
