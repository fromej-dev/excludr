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
    manager.connection_rooms.clear()
    manager.connection_users.clear()
    yield
    manager.active_connections.clear()
    manager.rooms.clear()
    manager.connection_rooms.clear()
    manager.connection_users.clear()


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


class _FakeSocket:
    """Stands in for a WebSocket in ConnectionManager unit tests."""

    def __init__(self, fail: bool = False):
        self.sent: list[str] = []
        self.fail = fail

    async def accept(self):
        pass

    async def send_text(self, text: str):
        if self.fail:
            raise RuntimeError("closed")
        self.sent.append(text)


@pytest.mark.asyncio
async def test_connection_manager_disconnect():
    """Disconnecting one connection removes only that connection from its rooms."""
    manager = ConnectionManager()
    tab1, tab2, other = _FakeSocket(), _FakeSocket(), _FakeSocket()
    await manager.connect(tab1, 1)
    await manager.connect(tab2, 1)
    await manager.connect(other, 2)
    await manager.join_room(tab1, "room1")
    await manager.join_room(tab2, "room1")
    await manager.join_room(other, "room1")
    await manager.join_room(tab2, "room2")

    manager.disconnect(tab2)

    assert manager.active_connections[1] == {tab1}
    assert manager.rooms["room1"] == {tab1, other}
    assert "room2" not in manager.rooms  # Empty room should be deleted
    assert tab2 not in manager.connection_rooms

    manager.disconnect(tab1)
    assert 1 not in manager.active_connections
    assert manager.get_room_users("room1") == {2}


@pytest.mark.asyncio
async def test_connection_manager_get_user_rooms():
    """A user's rooms are the rooms of all their connections."""
    manager = ConnectionManager()
    tab1, tab2 = _FakeSocket(), _FakeSocket()
    await manager.connect(tab1, 1)
    await manager.connect(tab2, 1)
    await manager.join_room(tab1, "room1")
    await manager.join_room(tab2, "room2")

    assert manager.get_user_rooms(1) == {"user_1", "room1", "room2"}
    assert manager.get_connection_rooms(tab1) == {"user_1", "room1"}
    assert manager.get_user_rooms(999) == set()


@pytest.mark.asyncio
async def test_connection_manager_get_room_users():
    """Room users are distinct users, however many tabs each has in the room."""
    manager = ConnectionManager()
    sockets = {_FakeSocket(): 1, _FakeSocket(): 1, _FakeSocket(): 2}
    for ws, user_id in sockets.items():
        await manager.connect(ws, user_id)
        await manager.join_room(ws, "test_room")

    assert manager.get_room_users("test_room") == {1, 2}
    assert manager.get_room_users("non_existent") == set()


@pytest.mark.asyncio
async def test_connection_manager_broadcast_skips_dead_connection():
    """A connection that fails to send does not stop the rest of the room."""
    manager = ConnectionManager()
    dead, alive = _FakeSocket(fail=True), _FakeSocket()
    await manager.connect(dead, 1)
    await manager.connect(alive, 2)
    await manager.join_room(dead, "room")
    await manager.join_room(alive, "room")

    await manager.broadcast_to_room("hello", "room")

    assert alive.sent == ["hello"]


def test_websocket_second_tab_does_not_steal_messages(
    client: TestClient, a_user, a_project, token_for
):
    """With two tabs open, both get project events; closing one keeps the other live."""
    import asyncio

    from app.features.websocket.services import NotificationService

    user = a_user()
    project = a_project(user)
    room = f"project_{project.id}"
    token = token_for(user)

    def notify(text: str) -> None:
        asyncio.run(NotificationService.notify_room(room_name=room, message=text))

    with client.websocket_connect(f"/api/v1/ws?token={token}") as tab1:
        tab1.receive_text()
        assert _send(tab1, type="join_room", room=room)["type"] == MessageType.INFO

        with client.websocket_connect(f"/api/v1/ws?token={token}") as tab2:
            tab2.receive_text()
            # The second tab's own replies go to it alone
            joined = _send(tab2, type="join_room", room=room)
            assert joined["type"] == MessageType.INFO
            notify("both tabs")
            assert json.loads(tab1.receive_text())["message"] == "both tabs"
            assert json.loads(tab2.receive_text())["message"] == "both tabs"

            # Leaving in one tab does not take the room away from the other
            _send(tab2, type="leave_room", room=room)
            notify("first tab only")
            assert json.loads(tab1.receive_text())["message"] == "first tab only"

        # The second tab closed: the first is still connected and in its room
        notify("after close")
        assert json.loads(tab1.receive_text())["message"] == "after close"
