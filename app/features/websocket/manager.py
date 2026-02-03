from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections and rooms."""

    def __init__(self):
        # Store active connections by user_id
        self.active_connections: Dict[int, WebSocket] = {}
        # Store rooms: room_name -> set of user_ids
        self.rooms: Dict[str, Set[int]] = {}
        # Store user's rooms: user_id -> set of room_names
        self.user_rooms: Dict[int, Set[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept WebSocket connection and add user to their default room."""
        await websocket.accept()
        self.active_connections[user_id] = websocket

        # Add user to their default room (user_id as room name)
        default_room = f"user_{user_id}"
        await self.join_room(user_id, default_room)

    def disconnect(self, user_id: int):
        """Remove user from all rooms and close connection."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]

        # Remove user from all rooms
        if user_id in self.user_rooms:
            for room in list(self.user_rooms[user_id]):
                self.leave_room(user_id, room)
            del self.user_rooms[user_id]

    async def join_room(self, user_id: int, room_name: str):
        """Add a user to a specific room."""
        if room_name not in self.rooms:
            self.rooms[room_name] = set()
        self.rooms[room_name].add(user_id)

        if user_id not in self.user_rooms:
            self.user_rooms[user_id] = set()
        self.user_rooms[user_id].add(room_name)

    def leave_room(self, user_id: int, room_name: str):
        """Remove a user from a specific room."""
        if room_name in self.rooms and user_id in self.rooms[room_name]:
            self.rooms[room_name].remove(user_id)
            # Clean up empty rooms
            if not self.rooms[room_name]:
                del self.rooms[room_name]

        if user_id in self.user_rooms and room_name in self.user_rooms[user_id]:
            self.user_rooms[user_id].remove(room_name)

    async def send_personal_message(self, message: str, user_id: int):
        """Send a message to a specific user."""
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            await websocket.send_text(message)

    async def broadcast_to_room(self, message: str, room_name: str):
        """Send a message to all users in a specific room."""
        if room_name in self.rooms:
            for user_id in self.rooms[room_name]:
                await self.send_personal_message(message, user_id)

    async def broadcast_to_all(self, message: str):
        """Send a message to all connected users."""
        for user_id in self.active_connections:
            await self.send_personal_message(message, user_id)

    def get_user_rooms(self, user_id: int) -> Set[str]:
        """Get all rooms a user is in."""
        return self.user_rooms.get(user_id, set())

    def get_room_users(self, room_name: str) -> Set[int]:
        """Get all users in a specific room."""
        return self.rooms.get(room_name, set())


# Global connection manager instance
manager = ConnectionManager()
