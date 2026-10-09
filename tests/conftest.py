"""
Test configuratie - Fixtures voor pytest.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.models.base import Base
from shared.models.user import User, UserRole
from shared.database import get_db
from services.api.auth import hash_password


# In-memory SQLite voor tests (sneller dan PostgreSQL)
TEST_DB_URL = "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true"

engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Maak tabellen aan voor elke test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    """Database sessie fixture."""
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db: AsyncSession):
    """Maak een testgebruiker aan."""
    user = User(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        username="dr.test",
        display_name="Dr. Test",
        role=UserRole.arts,
        password_hash=hash_password("test123"),
    )
    db.add(user)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    """FastAPI test client met database override."""
    from services.api.main import app

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user: User):
    """Genereer auth headers voor een ingelogde testgebruiker."""
    from services.api.auth import create_access_token
    token, _ = create_access_token(str(test_user.id), test_user.role.value)
    return {"Authorization": f"Bearer {token}"}
