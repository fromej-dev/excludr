from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


class MessageType(str, Enum):
    """Types of WebSocket messages."""

    TEXT = "text"
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    ROOM_MESSAGE = "room_message"
    BROADCAST = "broadcast"
    ERROR = "error"
    INFO = "info"
    NOTIFICATION = "notification"


class NotificationLevel(str, Enum):
    """Notification severity levels."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class WebSocketMessage(BaseModel):
    """WebSocket message schema."""

    type: MessageType
    data: Any
    room: Optional[str] = None


class WebSocketResponse(BaseModel):
    """WebSocket response schema."""

    type: MessageType
    message: str
    data: Optional[Any] = None
    room: Optional[str] = None
