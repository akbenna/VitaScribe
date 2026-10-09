"""
Seed script - Maakt initiële gebruiker(s) aan in productie database.

Gebruik:
    python scripts/seed_production.py

Leest DATABASE_URL uit environment (Railway zet dit automatisch).
"""

import asyncio
import os
import sys
import uuid

# Zorg dat imports werken vanuit scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.database import engine, async_session, init_db
from shared.models.user import User, UserRole
from services.api.auth import hash_password
from sqlalchemy import select


async def seed():
    """Maak standaard admin en arts accounts aan."""
    await init_db()

    async with async_session() as db:
        # Check of er al gebruikers bestaan
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none():
            print("[seed] Database bevat al gebruikers - overgeslagen.")
            return

        # Admin gebruiker
        admin_password = os.getenv("ADMIN_PASSWORD", "changeme123!")
        admin = User(
            id=uuid.uuid4(),
            username="admin",
            display_name="Beheerder",
            role=UserRole.beheerder,
            password_hash=hash_password(admin_password),
            is_active=True,
        )

        # Eerste arts account
        arts_password = os.getenv("ARTS_PASSWORD", "changeme123!")
        arts = User(
            id=uuid.uuid4(),
            username="arts1",
            display_name="Dr. Huisarts",
            role=UserRole.arts,
            password_hash=hash_password(arts_password),
            is_active=True,
        )

        db.add_all([admin, arts])
        await db.commit()

        print(f"[seed] Gebruikers aangemaakt:")
        print(f"  - admin    (beheerder)  wachtwoord: {admin_password}")
        print(f"  - arts1    (arts)        wachtwoord: {arts_password}")
        print()
        print("[seed] BELANGRIJK: Wijzig de wachtwoorden na eerste login!")
        print("[seed] Stel ADMIN_PASSWORD en ARTS_PASSWORD in als env vars voor veilige seed.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
