import pytest
import pytest_asyncio
from httpx import AsyncClient
from main import app
from database import get_database
from config import get_settings

settings = get_settings()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_db():
    db = await get_database()
    yield db
    # Cleanup after tests
    await db.users.delete_many({"username": {"$regex": "^test_"}})
    await db.stories.delete_many({})
    await db.refresh_tokens.delete_many({})


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "test_user1",
            "password": "testpass123"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "test_user1"
    assert "anonymous_name" in data
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    # Register first user
    await client.post(
        "/api/auth/register",
        json={
            "username": "test_user2",
            "password": "testpass123"
        }
    )
    
    # Try to register with same username
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "test_user2",
            "password": "testpass123"
        }
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_user(client: AsyncClient):
    # Register user
    await client.post(
        "/api/auth/register",
        json={
            "username": "test_user3",
            "password": "testpass123"
        }
    )
    
    # Login
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "test_user3",
            "password": "testpass123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    # Register user
    await client.post(
        "/api/auth/register",
        json={
            "username": "test_user4",
            "password": "testpass123"
        }
    )
    
    # Login with wrong password
    response = await client.post(
        "/api/auth/login",
        json={
            "username": "test_user4",
            "password": "wrongpassword"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_login(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        json={
            "username": settings.admin_username,
            "password": settings.admin_password
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient):
    # Register and login
    await client.post(
        "/api/auth/register",
        json={
            "username": "test_user5",
            "password": "testpass123"
        }
    )
    
    login_response = await client.post(
        "/api/auth/login",
        json={
            "username": "test_user5",
            "password": "testpass123"
        }
    )
    token = login_response.json()["access_token"]
    
    # Get current user
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "test_user5"


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    # Register and login
    await client.post(
        "/api/auth/register",
        json={
            "username": "test_user6",
            "password": "testpass123"
        }
    )
    
    login_response = await client.post(
        "/api/auth/login",
        json={
            "username": "test_user6",
            "password": "testpass123"
        }
    )
    refresh_token = login_response.json()["refresh_token"]
    
    # Refresh token
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    # Register and login
    await client.post(
        "/api/auth/register",
        json={
            "username": "test_user7",
            "password": "testpass123"
        }
    )
    
    login_response = await client.post(
        "/api/auth/login",
        json={
            "username": "test_user7",
            "password": "testpass123"
        }
    )
    token = login_response.json()["access_token"]
    
    # Logout
    response = await client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
