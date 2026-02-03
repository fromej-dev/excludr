import json
import pytest
from fastapi.testclient import TestClient

from app.features.websocket.manager import ConnectionManager
from app.features.websocket.schemas import MessageType


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


def test_websocket_connect_with_valid_token(client: TestClient, a_user, token_for):
    """Test WebSocket connection with valid JWT token."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Receive welcome message
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["type"] == MessageType.INFO
        assert "Connected successfully" in response["message"]
        assert response["data"]["user_id"] == user.id
        assert f"user_{user.id}" in response["data"]["rooms"]


def test_websocket_connect_with_invalid_token(client: TestClient):
    """Test WebSocket connection rejection with invalid token."""
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws?token=invalid_token"):
            pass


def test_websocket_connect_without_token(client: TestClient):
    """Test WebSocket connection rejection without token."""
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws"):
            pass


def test_websocket_echo_message(client: TestClient, a_user, token_for):
    """Test sending a text message and receiving echo."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        # Send text message
        message = {"type": "text", "data": "Hello, WebSocket!"}
        websocket.send_text(json.dumps(message))

        # Receive echo
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["type"] == MessageType.TEXT
        assert "Echo: Hello, WebSocket!" in response["message"]


def test_websocket_join_room(client: TestClient, a_user, token_for):
    """Test joining a custom room."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        # Join a room
        message = {"type": "join_room", "room": "test_room"}
        websocket.send_text(json.dumps(message))

        # Receive confirmation
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["type"] == MessageType.INFO
        assert "Joined room: test_room" in response["message"]
        assert "test_room" in response["data"]["rooms"]
        assert f"user_{user.id}" in response["data"]["rooms"]


def test_websocket_leave_room(client: TestClient, a_user, token_for):
    """Test leaving a room."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        # Join a room
        join_message = {"type": "join_room", "room": "test_room"}
        websocket.send_text(json.dumps(join_message))
        websocket.receive_text()  # Skip confirmation

        # Leave the room
        leave_message = {"type": "leave_room", "room": "test_room"}
        websocket.send_text(json.dumps(leave_message))

        # Receive confirmation
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["type"] == MessageType.INFO
        assert "Left room: test_room" in response["message"]
        assert "test_room" not in response["data"]["rooms"]


def test_websocket_room_message(client: TestClient, a_user, token_for):
    """Test sending a message to a room with multiple users."""
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
        room_name = "shared_room"
        join_message = {"type": "join_room", "room": room_name}

        ws1.send_text(json.dumps(join_message))
        ws1.receive_text()  # Skip confirmation

        ws2.send_text(json.dumps(join_message))
        ws2.receive_text()  # Skip confirmation

        # User 1 sends a message to the room
        room_message = {
            "type": "room_message",
            "room": room_name,
            "data": "Hello everyone!",
        }
        ws1.send_text(json.dumps(room_message))

        # Both users should receive the message
        data1 = ws1.receive_text()
        response1 = json.loads(data1)
        assert response1["type"] == MessageType.ROOM_MESSAGE
        assert response1["message"] == "Hello everyone!"
        assert response1["data"]["from_user_id"] == user1.id

        data2 = ws2.receive_text()
        response2 = json.loads(data2)
        assert response2["type"] == MessageType.ROOM_MESSAGE
        assert response2["message"] == "Hello everyone!"
        assert response2["data"]["from_user_id"] == user1.id


def test_websocket_broadcast(client: TestClient, a_user, token_for):
    """Test broadcasting a message to all connected users."""
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

        # User 1 broadcasts a message
        broadcast_message = {"type": "broadcast", "data": "Broadcast to all!"}
        ws1.send_text(json.dumps(broadcast_message))

        # Both users should receive the broadcast
        data1 = ws1.receive_text()
        response1 = json.loads(data1)
        assert response1["type"] == MessageType.BROADCAST
        assert response1["message"] == "Broadcast to all!"

        data2 = ws2.receive_text()
        response2 = json.loads(data2)
        assert response2["type"] == MessageType.BROADCAST
        assert response2["message"] == "Broadcast to all!"


def test_websocket_invalid_message_format(client: TestClient, a_user, token_for):
    """Test handling of invalid message format."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        # Send invalid JSON
        websocket.send_text("not a json")

        # Receive error message
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["type"] == MessageType.ERROR
        assert "Invalid message format" in response["message"]


def test_websocket_join_room_without_room_name(client: TestClient, a_user, token_for):
    """Test joining room without providing room name."""
    user = a_user()
    token = token_for(user)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Skip welcome message
        websocket.receive_text()

        # Try to join without room name
        message = {"type": "join_room"}
        websocket.send_text(json.dumps(message))

        # Receive error message
        data = websocket.receive_text()
        response = json.loads(data)

        assert response["type"] == MessageType.ERROR
        assert "Room name is required" in response["message"]


def test_connection_manager_disconnect():
    """Test ConnectionManager disconnect functionality."""
    manager = ConnectionManager()

    # Mock user_id and websocket
    user_id = 1

    # Add user to rooms
    manager.user_rooms[user_id] = {"room1", "room2"}
    manager.rooms["room1"] = {user_id, 2}
    manager.rooms["room2"] = {user_id}

    # Disconnect user
    manager.disconnect(user_id)

    # Verify user is removed from all rooms
    assert user_id not in manager.user_rooms
    assert user_id not in manager.rooms.get("room1", set())
    assert "room2" not in manager.rooms  # Empty room should be deleted
    assert user_id not in manager.active_connections


def test_connection_manager_get_user_rooms():
    """Test getting user's rooms."""
    manager = ConnectionManager()

    user_id = 1
    manager.user_rooms[user_id] = {"room1", "room2"}

    rooms = manager.get_user_rooms(user_id)
    assert rooms == {"room1", "room2"}

    # Test non-existent user
    rooms = manager.get_user_rooms(999)
    assert rooms == set()


def test_connection_manager_get_room_users():
    """Test getting room's users."""
    manager = ConnectionManager()

    room_name = "test_room"
    manager.rooms[room_name] = {1, 2, 3}

    users = manager.get_room_users(room_name)
    assert users == {1, 2, 3}

    # Test non-existent room
    users = manager.get_room_users("non_existent")
    assert users == set()
