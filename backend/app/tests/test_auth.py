import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    # Register
    resp = await client.post("/api/auth/register", json={
        "email": "alice@example.com",
        "display_name": "Alice",
        "password": "secret123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert data["display_name"] == "Alice"
    assert "user_id" in data

    # Login
    resp = await client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "secret123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()

    # Get me
    token = resp.json()["access_token"]
    resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "dup@example.com",
        "display_name": "User1",
        "password": "pass1",
    })
    resp = await client.post("/api/auth/register", json={
        "email": "dup@example.com",
        "display_name": "User2",
        "password": "pass2",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "wrongpw@example.com",
        "display_name": "User",
        "password": "correct",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "wrongpw@example.com",
        "password": "wrong",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    resp = await client.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_returns_refresh_token(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "refresh1@example.com",
        "display_name": "R1",
        "password": "pw",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "refresh1@example.com",
        "password": "pw",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["access_token"] != data["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_issues_new_access_token(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "refresh2@example.com",
        "display_name": "R2",
        "password": "pw",
    })
    login = await client.post("/api/auth/login", json={
        "email": "refresh2@example.com",
        "password": "pw",
    })
    refresh_token = login.json()["refresh_token"]

    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]

    # New access token lets us call /api/me
    me = await client.get("/api/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200
    assert me.json()["email"] == "refresh2@example.com"


@pytest.mark.asyncio
async def test_refresh_rejects_access_token(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "refresh3@example.com",
        "display_name": "R3",
        "password": "pw",
    })
    login = await client.post("/api/auth/login", json={
        "email": "refresh3@example.com",
        "password": "pw",
    })
    access = login.json()["access_token"]

    resp = await client.post("/api/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_access_endpoint_rejects_refresh_token(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "refresh4@example.com",
        "display_name": "R4",
        "password": "pw",
    })
    login = await client.post("/api/auth/login", json={
        "email": "refresh4@example.com",
        "password": "pw",
    })
    refresh_token = login.json()["refresh_token"]

    resp = await client.get(
        "/api/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_garbage(client: AsyncClient):
    resp = await client.post("/api/auth/refresh", json={"refresh_token": "not.a.jwt"})
    assert resp.status_code == 401
