from typing import Any, Optional

from .manager import manager
from .schemas import MessageType, NotificationLevel, WebSocketResponse


class NotificationService:
    """
    Service for sending notifications from backend to frontend via WebSocket.

    This service can be used from anywhere in your backend code (API endpoints,
    Celery tasks, services, etc.) to send real-time notifications to users.

    Example usage:
        # Send a notification to a specific user
        await NotificationService.notify_user(
            user_id=123,
            message="Your project upload is complete!",
            level=NotificationLevel.SUCCESS
        )

        # Send a notification to all users in a room
        await NotificationService.notify_room(
            room_name="project_456",
            message="New screening result available",
            level=NotificationLevel.INFO
        )

        # Broadcast to all connected users
        await NotificationService.broadcast(
            message="System maintenance in 5 minutes",
            level=NotificationLevel.WARNING
        )
    """

    @staticmethod
    async def notify_user(
        user_id: int,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        data: Optional[Any] = None,
    ) -> bool:
        """
        Send a notification to a specific user.

        Args:
            user_id: The ID of the user to notify
            message: The notification message
            level: Notification severity level
            data: Optional additional data to include

        Returns:
            True if user is connected and notification was sent, False otherwise
        """
        if user_id not in manager.active_connections:
            return False

        response = WebSocketResponse(
            type=MessageType.INFO,
            message=message,
            data={
                "level": level.value,
                "notification": True,
                **(data or {}),
            },
        )
        await manager.send_personal_message(response.model_dump_json(), user_id)
        return True

    @staticmethod
    async def notify_room(
        room_name: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        data: Optional[Any] = None,
    ) -> int:
        """
        Send a notification to all users in a specific room.

        Args:
            room_name: The name of the room
            message: The notification message
            level: Notification severity level
            data: Optional additional data to include

        Returns:
            Number of users notified
        """
        if room_name not in manager.rooms:
            return 0

        response = WebSocketResponse(
            type=MessageType.ROOM_MESSAGE,
            message=message,
            room=room_name,
            data={
                "level": level.value,
                "notification": True,
                **(data or {}),
            },
        )
        await manager.broadcast_to_room(response.model_dump_json(), room_name)
        return len(manager.rooms[room_name])

    @staticmethod
    async def broadcast(
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        data: Optional[Any] = None,
    ) -> int:
        """
        Broadcast a notification to all connected users.

        Args:
            message: The notification message
            level: Notification severity level
            data: Optional additional data to include

        Returns:
            Number of users notified
        """
        response = WebSocketResponse(
            type=MessageType.BROADCAST,
            message=message,
            data={
                "level": level.value,
                "notification": True,
                **(data or {}),
            },
        )
        await manager.broadcast_to_all(response.model_dump_json())
        return len(manager.active_connections)

    @staticmethod
    async def notify_user_in_room(
        user_id: int,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        data: Optional[Any] = None,
    ) -> bool:
        """
        Send a notification to a user's personal room (user_{user_id}).

        This is useful for ensuring the notification is sent to the user's default room.

        Args:
            user_id: The ID of the user to notify
            message: The notification message
            level: Notification severity level
            data: Optional additional data to include

        Returns:
            True if notification was sent, False otherwise
        """
        room_name = f"user_{user_id}"
        count = await NotificationService.notify_room(
            room_name=room_name, message=message, level=level, data=data
        )
        return count > 0

    @staticmethod
    def is_user_connected(user_id: int) -> bool:
        """Check if a user is currently connected via WebSocket."""
        return user_id in manager.active_connections

    @staticmethod
    def get_connected_users() -> set[int]:
        """Get set of all connected user IDs."""
        return set(manager.active_connections.keys())

    @staticmethod
    def get_room_members(room_name: str) -> set[int]:
        """Get set of all user IDs in a specific room."""
        return manager.get_room_users(room_name)
