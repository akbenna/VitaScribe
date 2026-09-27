"""
VitaScribe Cloud API - Usage log (NEN 7513)

Records WHO used WHICH function WHEN, and with which outcome; never the
content (no audio, text, names or dossier data). One JSON line per event on
stdout and, when AUDIT_LOG_PATH is set, appended to that file as well.

Railway keeps stdout only briefly, which is not enough for NEN 7513. With the
register on (DATABASE_URL) every event also goes to the table vs_auditlog. The
database refuses updates and truncation there, and rows younger than a year
cannot be deleted. Rows older than AUDIT_BEWAARDAGEN (default 1825, five
years; at least 365) are removed at most once a day.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Optional, Set

import structlog

logger = structlog.get_logger()

_ALLOWED_DETAIL = {"kind", "mode", "provider", "chars", "seconds", "status", "consent", "aanvrager", "sections"}


def log_event(user: str, action: str, **detail: Any) -> None:
    """Write one usage event. Only whitelisted, content-free details are kept."""
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "user": user or "onbekend",
        "action": action,
    }
    for key, value in detail.items():
        if key in _ALLOWED_DETAIL and isinstance(value, (str, int, float, bool)) and len(str(value)) <= 40:
            event[key] = value
    logger.info("audit", **event)
    path = os.getenv("AUDIT_LOG_PATH")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError as exc:  # never let logging break care
            logger.error("audit.write_failed", error=str(exc))
    _to_register(event)


# ── Persistent copy in the register ──

_pending: Set["asyncio.Task[None]"] = set()
_last_cleanup: Optional[float] = None
CLEANUP_INTERVAL = 24 * 3600


def retention_days() -> int:
    """How long rows stay; never less than the year the database enforces."""
    try:
        days = int(os.getenv("AUDIT_BEWAARDAGEN") or 1825)
    except ValueError:
        days = 1825
    return max(days, 365)


def _to_register(event: dict) -> None:
    from . import register

    if not register.actief():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # no event loop (a script): stdout and file only
        return
    task = loop.create_task(_store(event))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _store(event: dict) -> None:
    from . import register

    details = {k: v for k, v in event.items() if k not in ("ts", "user", "action")}
    try:
        await register.execute(
            "INSERT INTO vs_auditlog (gebruiker, handeling, details) VALUES ($1, $2, $3::jsonb)",
            event["user"], event["action"], json.dumps(details, ensure_ascii=False),
        )
    except Exception as exc:  # never let logging break care
        logger.error("audit.register_failed", error=str(exc))
        return
    await _cleanup()


async def _cleanup() -> None:
    global _last_cleanup
    from . import register

    now = time.time()
    if _last_cleanup is not None and now - _last_cleanup < CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    try:
        await register.execute(
            "DELETE FROM vs_auditlog WHERE op < now() - make_interval(days => $1)", retention_days())
    except Exception as exc:
        logger.error("audit.cleanup_failed", error=str(exc))


async def flush() -> None:
    """Wait until every event written so far is in the register (tests, shutdown)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
