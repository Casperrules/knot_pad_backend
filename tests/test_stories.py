import pytest
import pytest_asyncio
from httpx import AsyncClient
from main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    # Register and login a test user
    await client.post(
        "/api/auth/register",
        json={
            "username": "story_test_user",
            "password": "testpass123"
        }
    )
    
    login_response = await client.post(
        "/api/auth/login",
        json={
            "username": "story_test_user",
            "password": "testpass123"
        }
    )
    return login_response.json()["access_token"]


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    # Login as admin
    from config import get_settings
    settings = get_settings()
    
    login_response = await client.post(
        "/api/auth/login",
        json={
            "username": settings.admin_username,
            "password": settings.admin_password
        }
    )
    return login_response.json()["access_token"]


@pytest.mark.asyncio
async def test_create_story(client: AsyncClient, auth_token: str):
    response = await client.post(
        "/api/stories/",
        json={
            "title": "Test Story",
            "content": "This is a test story content",
            "images": [],
            "tags": ["test", "fiction"]
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Story"
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_update_story(client: AsyncClient, auth_token: str):
    # Create story
    create_response = await client.post(
        "/api/stories/",
        json={
            "title": "Original Title",
            "content": "Original content",
            "images": [],
            "tags": []
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    story_id = create_response.json()["id"]
    
    # Update story
    response = await client.put(
        f"/api/stories/{story_id}",
        json={
            "title": "Updated Title",
            "content": "Updated content"
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_submit_story(client: AsyncClient, auth_token: str):
    # Create story
    create_response = await client.post(
        "/api/stories/",
        json={
            "title": "Story to Submit",
            "content": "Content for submission",
            "images": [],
            "tags": []
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    story_id = create_response.json()["id"]
    
    # Submit story
    response = await client.post(
        f"/api/stories/{story_id}/submit",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_my_stories(client: AsyncClient, auth_token: str):
    # Create a story
    await client.post(
        "/api/stories/",
        json={
            "title": "My Story",
            "content": "My content",
            "images": [],
            "tags": []
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    # Get my stories
    response = await client.get(
        "/api/stories/my-stories",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "stories" in data
    assert len(data["stories"]) > 0


@pytest.mark.asyncio
async def test_get_pending_stories_admin(client: AsyncClient, admin_token: str):
    response = await client.get(
        "/api/stories/pending",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "stories" in data


@pytest.mark.asyncio
async def test_approve_story(client: AsyncClient, auth_token: str, admin_token: str):
    # Create and submit story
    create_response = await client.post(
        "/api/stories/",
        json={
            "title": "Story to Approve",
            "content": "Content to approve",
            "images": [],
            "tags": []
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    story_id = create_response.json()["id"]
    
    await client.post(
        f"/api/stories/{story_id}/submit",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    # Approve story as admin
    response = await client.post(
        f"/api/stories/{story_id}/approve",
        json={"approved": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_feed(client: AsyncClient, auth_token: str):
    response = await client.get(
        "/api/stories/feed",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "stories" in data
