import json
import pytest
from fastapi.testclient import TestClient

from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel, MessageType


@pytest.fixture(autouse=True)
def reset_connection_manager():
    """Reset the connection manager before each test."""
    from app.features.websocket.manager import manager

    manager.active_connections.clear()
    manager.rooms.clear()
    manager.user_rooms.clear()
    yield
    manager.active_connections.clear()
    manager.rooms.clear()
    manager.user_rooms.clear()


@pytest.mark.asyncio
async def test_notify_user_success(client: TestClient, a_user, token_for):
    """Test sending notification to a connected user."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        # Send notification from backend
        result = await NotificationService.notify_user(
            user_id=user.id,
            message="Test notification",
            level=NotificationLevel.SUCCESS,
            data={"custom_field": "custom_value"},
        )

        assert result is True

        # User should receive the notification
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["type"] == MessageType.INFO
        assert response["message"] == "Test notification"
        assert response["data"]["level"] == NotificationLevel.SUCCESS.value
        assert response["data"]["notification"] is True
        assert response["data"]["custom_field"] == "custom_value"


@pytest.mark.asyncio
async def test_notify_user_not_connected():
    """Test sending notification to a user who is not connected."""
    result = await NotificationService.notify_user(
        user_id=999, message="Test notification", level=NotificationLevel.INFO
    )

    assert result is False


@pytest.mark.asyncio
async def test_notify_user_with_different_levels(client: TestClient, a_user, token_for):
    """Test sending notifications with different severity levels."""
    user = a_user()
    token = token_for(user)

    levels = [
        NotificationLevel.INFO,
        NotificationLevel.SUCCESS,
        NotificationLevel.WARNING,
        NotificationLevel.ERROR,
    ]

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        for level in levels:
            await NotificationService.notify_user(
                user_id=user.id, message=f"Test {level.value}", level=level
            )

            data = websocket.receive_text()
            response = json.loads(data)

            assert response["data"]["level"] == level.value
            assert f"Test {level.value}" in response["message"]


@pytest.mark.asyncio
async def test_notify_room(client: TestClient, a_user, token_for):
    """Test sending notification to all users in a room."""
    user1 = a_user()
    user2 = a_user()
    token1 = token_for(user1)
    token2 = token_for(user2)

    with client.websocket_connect(
        f"/api/v1/ws?token={token1}"
    ) as ws1, client.websocket_connect(f"/api/v1/ws?token={token2}") as ws2:
        # Skip welcome messages
        ws1.receive_text()
        ws2.receive_text()

        # Both users join the same room
        room_name = "test_room"
        join_message = {"type": "join_room", "room": room_name}

        ws1.send_text(json.dumps(join_message))
        ws1.receive_text()  # Skip confirmation

        ws2.send_text(json.dumps(join_message))
        ws2.receive_text()  # Skip confirmation

        # Send notification to the room
        count = await NotificationService.notify_room(
            room_name=room_name,
            message="Room notification",
            level=NotificationLevel.INFO,
            data={"room_data": "test"},
        )

        assert count == 2

        # Both users should receive the notification
        data1 = ws1.receive_text()
        response1 = json.loads(data1)
        assert response1["message"] == "Room notification"
        assert response1["data"]["notification"] is True
        assert response1["room"] == room_name

        data2 = ws2.receive_text()
        response2 = json.loads(data2)
        assert response2["message"] == "Room notification"
        assert response2["data"]["notification"] is True


@pytest.mark.asyncio
async def test_notify_room_not_exists():
    """Test sending notification to a non-existent room."""
    count = await NotificationService.notify_room(
        room_name="non_existent_room",
        message="Test",
        level=NotificationLevel.INFO,
    )

    assert count == 0


@pytest.mark.asyncio
async def test_broadcast(client: TestClient, a_user, token_for):
    """Test broadcasting notification to all connected users."""
    user1 = a_user()
    user2 = a_user()
    user3 = a_user()
    token1 = token_for(user1)
    token2 = token_for(user2)
    token3 = token_for(user3)

    with client.websocket_connect(
        f"/api/v1/ws?token={token1}"
    ) as ws1, client.websocket_connect(
        f"/api/v1/ws?token={token2}"
    ) as ws2, client.websocket_connect(
        f"/api/v1/ws?token={token3}"
    ) as ws3:
        # Skip welcome messages
        ws1.receive_text()
        ws2.receive_text()
        ws3.receive_text()

        # Broadcast to all users
        count = await NotificationService.broadcast(
            message="System-wide notification",
            level=NotificationLevel.WARNING,
            data={"broadcast_id": 123},
        )

        assert count == 3

        # All users should receive the broadcast
        for ws in [ws1, ws2, ws3]:
            data = ws.receive_text()
            response = json.loads(data)
            assert response["type"] == MessageType.BROADCAST
            assert response["message"] == "System-wide notification"
            assert response["data"]["level"] == NotificationLevel.WARNING.value
            assert response["data"]["notification"] is True
            assert response["data"]["broadcast_id"] == 123


@pytest.mark.asyncio
async def test_notify_user_in_room(client: TestClient, a_user, token_for):
    """Test sending notification to user's personal room."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        # Notify user in their personal room
        result = await NotificationService.notify_user_in_room(
            user_id=user.id,
            message="Personal room notification",
            level=NotificationLevel.INFO,
        )

        assert result is True

        # User should receive the notification
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["message"] == "Personal room notification"
        assert response["room"] == f"user_{user.id}"


@pytest.mark.asyncio
async def test_is_user_connected(client: TestClient, a_user, token_for):
    """Test checking if a user is connected."""
    user = a_user()
    token = token_for(user)

    # User not connected
    assert NotificationService.is_user_connected(user.id) is False

    with client.websocket_connect(f"/api/v1/ws?token={token}"):
        # User connected
        assert NotificationService.is_user_connected(user.id) is True

    # User disconnected
    assert NotificationService.is_user_connected(user.id) is False


@pytest.mark.asyncio
async def test_get_connected_users(client: TestClient, a_user, token_for):
    """Test getting all connected users."""
    user1 = a_user()
    user2 = a_user()
    token1 = token_for(user1)
    token2 = token_for(user2)

    # No users connected
    connected = NotificationService.get_connected_users()
    assert len(connected) == 0

    with client.websocket_connect(f"/api/v1/ws?token={token1}"):
        # One user connected
        connected = NotificationService.get_connected_users()
        assert len(connected) == 1
        assert user1.id in connected

        with client.websocket_connect(f"/api/v1/ws?token={token2}"):
            # Two users connected
            connected = NotificationService.get_connected_users()
            assert len(connected) == 2
            assert user1.id in connected
            assert user2.id in connected

        # One user disconnected
        connected = NotificationService.get_connected_users()
        assert len(connected) == 1
        assert user1.id in connected


@pytest.mark.asyncio
async def test_get_room_members(client: TestClient, a_user, token_for):
    """Test getting all members in a room."""
    user1 = a_user()
    user2 = a_user()
    token1 = token_for(user1)
    token2 = token_for(user2)

    room_name = "test_room"

    with client.websocket_connect(
        f"/api/v1/ws?token={token1}"
    ) as ws1, client.websocket_connect(f"/api/v1/ws?token={token2}") as ws2:
        # Skip welcome messages
        ws1.receive_text()
        ws2.receive_text()

        # Initially, room doesn't exist
        members = NotificationService.get_room_members(room_name)
        assert len(members) == 0

        # User 1 joins room
        join_message = {"type": "join_room", "room": room_name}
        ws1.send_text(json.dumps(join_message))
        ws1.receive_text()  # Skip confirmation

        members = NotificationService.get_room_members(room_name)
        assert len(members) == 1
        assert user1.id in members

        # User 2 joins room
        ws2.send_text(json.dumps(join_message))
        ws2.receive_text()  # Skip confirmation

        members = NotificationService.get_room_members(room_name)
        assert len(members) == 2
        assert user1.id in members
        assert user2.id in members


@pytest.mark.asyncio
async def test_notification_with_complex_data(client: TestClient, a_user, token_for):
    """Test sending notification with complex data structure."""
    user = a_user()
    token = token_for(user)

    complex_data = {
        "project_id": 123,
        "status": "completed",
        "results": {
            "total": 100,
            "passed": 85,
            "failed": 15,
        },
        "links": [
            {"name": "View Report", "url": "/reports/123"},
            {"name": "Download", "url": "/downloads/123"},
        ],
    }

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        await NotificationService.notify_user(
            user_id=user.id,
            message="Processing complete",
            level=NotificationLevel.SUCCESS,
            data=complex_data,
        )

        data = websocket.receive_text()
        response = json.loads(data)

        assert response["data"]["project_id"] == 123
        assert response["data"]["status"] == "completed"
        assert response["data"]["results"]["total"] == 100
        assert len(response["data"]["links"]) == 2
