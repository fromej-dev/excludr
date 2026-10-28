import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and rooms.

    A user may have several connections at once (one per browser tab), so rooms
    are joined per connection: one tab leaving a room or closing never affects
    the user's other tabs.
    """

    def __init__(self):
        # Open connections by user_id
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # Rooms: room_name -> connections in it
        self.rooms: Dict[str, Set[WebSocket]] = {}
        # Each connection's rooms
        self.connection_rooms: Dict[WebSocket, Set[str]] = {}
        # Owner of each connection
        self.connection_users: Dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept WebSocket connection and add it to the user's default room."""
        await websocket.accept()
        self.active_connections.setdefault(user_id, set()).add(websocket)
        self.connection_users[websocket] = user_id

        # Add the connection to the user's default room (user_id as room name)
        await self.join_room(websocket, f"user_{user_id}")

    def disconnect(self, websocket: WebSocket):
        """Forget a connection and remove it from all its rooms."""
        for room in list(self.connection_rooms.get(websocket, ())):
            self.leave_room(websocket, room)
        self.connection_rooms.pop(websocket, None)

        user_id = self.connection_users.pop(websocket, None)
        connections = self.active_connections.get(user_id)
        if connections is not None:
            connections.discard(websocket)
            if not connections:
                del self.active_connections[user_id]

    async def join_room(self, websocket: WebSocket, room_name: str):
        """Add a connection to a specific room."""
        self.rooms.setdefault(room_name, set()).add(websocket)
        self.connection_rooms.setdefault(websocket, set()).add(room_name)

    def leave_room(self, websocket: WebSocket, room_name: str):
        """Remove a connection from a specific room."""
        members = self.rooms.get(room_name)
        if members is not None and websocket in members:
            members.remove(websocket)
            # Clean up empty rooms
            if not members:
                del self.rooms[room_name]

        self.connection_rooms.get(websocket, set()).discard(room_name)

    async def send(self, websocket: WebSocket, message: str):
        """Send a message to one connection; a dead connection is skipped."""
        try:
            await websocket.send_text(message)
        except Exception:
            # Closed in the meantime; its own handler cleans it up
            logger.debug("Dropping message for a closed websocket", exc_info=True)

    async def send_personal_message(self, message: str, user_id: int):
        """Send a message to every connection of a user."""
        for websocket in list(self.active_connections.get(user_id, ())):
            await self.send(websocket, message)

    async def broadcast_to_room(self, message: str, room_name: str):
        """Send a message to all connections in a specific room."""
        for websocket in list(self.rooms.get(room_name, ())):
            await self.send(websocket, message)

    async def broadcast_to_all(self, message: str):
        """Send a message to all open connections."""
        for websocket in list(self.connection_users):
            await self.send(websocket, message)

    def get_connection_rooms(self, websocket: WebSocket) -> Set[str]:
        """Get all rooms a connection is in."""
        return set(self.connection_rooms.get(websocket, ()))

    def get_user_rooms(self, user_id: int) -> Set[str]:
        """Get all rooms any of a user's connections is in."""
        rooms: Set[str] = set()
        for websocket in self.active_connections.get(user_id, ()):
            rooms |= self.connection_rooms.get(websocket, set())
        return rooms

    def get_room_users(self, room_name: str) -> Set[int]:
        """Get all users with a connection in a specific room."""
        return {
            self.connection_users[ws]
            for ws in self.rooms.get(room_name, ())
            if ws in self.connection_users
        }


# Global connection manager instance
manager = ConnectionManager()
