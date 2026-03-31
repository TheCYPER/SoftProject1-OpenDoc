import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base

TEST_DB_PATH = "./test.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass


async def _override_get_db():
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    from app.api.deps import get_db
    from app.main import app

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session():
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """Register a test user and return auth headers."""
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/api/auth/register", json={
        "email": f"test_{unique}@example.com",
        "display_name": "Test User",
        "password": "testpass123",
    })
    assert resp.status_code == 201, f"Register failed: {resp.text}"

    resp = await client.post("/api/auth/login", json={
        "email": f"test_{unique}@example.com",
        "password": "testpass123",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def workspace_id(db_session: AsyncSession):
    """Create a test workspace and return its ID."""
    from app.models.workspace import Workspace
    ws = Workspace(name="Test Workspace")
    db_session.add(ws)
    await db_session.commit()
    await db_session.refresh(ws)
    return ws.workspace_id


@pytest_asyncio.fixture
async def user_bob(client: AsyncClient):
    """Register a second test user (Bob) and return headers + email."""
    unique = uuid.uuid4().hex[:8]
    email = f"bob_{unique}@example.com"
    resp = await client.post("/api/auth/register", json={
        "email": email,
        "display_name": "Bob",
        "password": "testpass123",
    })
    assert resp.status_code == 201, f"Bob register failed: {resp.text}"
    resp = await client.post("/api/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    assert resp.status_code == 200, f"Bob login failed: {resp.text}"
    return {"headers": {"Authorization": f"Bearer {resp.json()['access_token']}"}, "email": email}
