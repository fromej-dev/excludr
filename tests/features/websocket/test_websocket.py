import json
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws?token=invalid_token"):
            pass


def test_websocket_connect_without_token(client: TestClient):
    """Test WebSocket connection rejection without token."""
    with pytest.raises(WebSocketDisconnect):
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


def _send(ws, **message):
    ws.send_text(json.dumps(message))
    return json.loads(ws.receive_text())


def test_websocket_join_own_project_room(
    client: TestClient, a_user, a_project, token_for
):
    """Owners may join the room of a project they own."""
    user = a_user()
    project = a_project(user)

    with client.websocket_connect(f"/api/v1/ws?token={token_for(user)}") as ws:
        ws.receive_text()
        room = f"project_{project.id}"
        response = _send(ws, type="join_room", room=room)

        assert response["type"] == MessageType.INFO
        assert f"Joined room: {room}" in response["message"]
        assert room in response["data"]["rooms"]
        assert f"user_{user.id}" in response["data"]["rooms"]


def test_websocket_join_own_user_room(client: TestClient, a_user, token_for):
    user = a_user()
    with client.websocket_connect(f"/api/v1/ws?token={token_for(user)}") as ws:
        ws.receive_text()
        response = _send(ws, type="join_room", room=f"user_{user.id}")
        assert response["type"] == MessageType.INFO


@pytest.mark.parametrize(
    "kind", ["other_user", "other_project", "arbitrary", "missing"]
)
def test_websocket_join_unauthorized_room_denied(
    client: TestClient, a_user, a_project, token_for, kind
):
    """Users cannot join rooms of other users/projects or arbitrary rooms."""
    from app.features.websocket.manager import manager

    user, other = a_user(), a_user()
    other_project = a_project(other)
    room = {
        "other_user": f"user_{other.id}",
        "other_project": f"project_{other_project.id}",
        "arbitrary": "test_room",
        "missing": "project_999999",
    }[kind]

    with client.websocket_connect(f"/api/v1/ws?token={token_for(user)}") as ws:
        ws.receive_text()
        response = _send(ws, type="join_room", room=room)

        assert response["type"] == MessageType.ERROR
        assert room not in manager.get_user_rooms(user.id)
        assert user.id not in manager.get_room_users(room)


def test_websocket_leave_room(client: TestClient, a_user, a_project, token_for):
    """Test leaving a room."""
    user = a_user()
    room = f"project_{a_project(user).id}"

    with client.websocket_connect(f"/api/v1/ws?token={token_for(user)}") as ws:
        ws.receive_text()
        _send(ws, type="join_room", room=room)

        response = _send(ws, type="leave_room", room=room)

        assert response["type"] == MessageType.INFO
        assert f"Left room: {room}" in response["message"]
        assert room not in response["data"]["rooms"]


def test_websocket_room_message_to_joined_room(
    client: TestClient, a_user, a_project, token_for
):
    """A member can message a room they joined."""
    user = a_user()
    room = f"project_{a_project(user).id}"

    with client.websocket_connect(f"/api/v1/ws?token={token_for(user)}") as ws:
        ws.receive_text()
        _send(ws, type="join_room", room=room)

        response = _send(ws, type="room_message", room=room, data="Hello everyone!")

        assert response["type"] == MessageType.ROOM_MESSAGE
        assert response["message"] == "Hello everyone!"
        assert response["data"]["from_user_id"] == user.id


def test_websocket_room_message_to_foreign_room_denied(
    client: TestClient, a_user, a_project, token_for
):
    """Non-members cannot post into a room, and members never see the message."""
    victim, attacker = a_user(), a_user()
    room = f"project_{a_project(victim).id}"

    with (
        client.websocket_connect(f"/api/v1/ws?token={token_for(victim)}") as ws_victim,
        client.websocket_connect(f"/api/v1/ws?token={token_for(attacker)}") as ws_att,
    ):
        ws_victim.receive_text()
        ws_att.receive_text()
        _send(ws_victim, type="join_room", room=room)

        response = _send(ws_att, type="room_message", room=room, data="pwned")
        assert response["type"] == MessageType.ERROR

        # The victim's next frame is their own echo, not the attacker's message
        echo = _send(ws_victim, type="text", data="ping")
        assert echo["type"] == MessageType.TEXT


def test_websocket_broadcast_denied_for_regular_user(
    client: TestClient, a_user, token_for
):
    """Regular users cannot broadcast to everyone."""
    user1, user2 = a_user(), a_user()

    with (
        client.websocket_connect(f"/api/v1/ws?token={token_for(user1)}") as ws1,
        client.websocket_connect(f"/api/v1/ws?token={token_for(user2)}") as ws2,
    ):
        ws1.receive_text()
        ws2.receive_text()

        response = _send(ws1, type="broadcast", data="Broadcast to all!")
        assert response["type"] == MessageType.ERROR

        echo = _send(ws2, type="text", data="ping")
        assert echo["type"] == MessageType.TEXT


def test_websocket_broadcast_allowed_for_superuser(
    client: TestClient, a_user, token_for, session
):
    """Superusers can broadcast to all connected users."""
    admin, user2 = a_user(), a_user()
    admin.is_superuser = True
    session.add(admin)
    session.commit()

    with (
        client.websocket_connect(f"/api/v1/ws?token={token_for(admin)}") as ws1,
        client.websocket_connect(f"/api/v1/ws?token={token_for(user2)}") as ws2,
    ):
        ws1.receive_text()
        ws2.receive_text()

        ws1.send_text(json.dumps({"type": "broadcast", "data": "Broadcast to all!"}))

        for ws in (ws1, ws2):
            response = json.loads(ws.receive_text())
            assert response["type"] == MessageType.BROADCAST
            assert response["message"] == "Broadcast to all!"


def test_websocket_rejects_refresh_token(client: TestClient, a_user):
    from app.features.auth.services import create_refresh_token

    user = a_user()
    token = create_refresh_token({"sub": user.email})
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/ws?token={token}"):
            pass


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
