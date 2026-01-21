import json
from typing import Annotated

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status

from app.features.auth.services import verify_token_and_get_user
from app.features.users.services import UserServiceDep
from .manager import manager
from .schemas import MessageType, WebSocketMessage, WebSocketResponse

router = APIRouter(tags=["WebSocket"], prefix="/ws")


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Annotated[str, Query()],
    us: UserServiceDep,
):
    """
    WebSocket endpoint with room management.

    Authentication:
    - Pass JWT token as query parameter: ws://localhost:8000/api/v1/ws?token=YOUR_TOKEN

    Default behavior:
    - User is automatically added to a room named "user_{user_id}"

    Message format (JSON):
    {
        "type": "text|join_room|leave_room|room_message|broadcast",
        "data": "message content or data",
        "room": "room_name" (optional, required for room operations)
    }

    Message types:
    - text: Send a personal message back to the user
    - join_room: Join a specific room (requires "room" field)
    - leave_room: Leave a specific room (requires "room" field)
    - room_message: Send message to all users in a room (requires "room" field)
    - broadcast: Send message to all connected users
    """
    # Authenticate user using shared validation logic
    user = verify_token_and_get_user(token, us)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Connect user and add to default room
    await manager.connect(websocket, user.id)

    # Send welcome message
    welcome_response = WebSocketResponse(
        type=MessageType.INFO,
        message=f"Connected successfully. You are in room: user_{user.id}",
        data={"user_id": user.id, "rooms": list(manager.get_user_rooms(user.id))},
    )
    await websocket.send_text(welcome_response.model_dump_json())

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                # Parse message
                message = WebSocketMessage.model_validate_json(data)

                # Handle different message types
                if message.type == MessageType.TEXT:
                    # Echo message back to user
                    response = WebSocketResponse(
                        type=MessageType.TEXT,
                        message=f"Echo: {message.data}",
                    )
                    await manager.send_personal_message(
                        response.model_dump_json(), user.id
                    )

                elif message.type == MessageType.JOIN_ROOM:
                    if not message.room:
                        raise ValueError("Room name is required")
                    await manager.join_room(user.id, message.room)
                    response = WebSocketResponse(
                        type=MessageType.INFO,
                        message=f"Joined room: {message.room}",
                        room=message.room,
                        data={"rooms": list(manager.get_user_rooms(user.id))},
                    )
                    await manager.send_personal_message(
                        response.model_dump_json(), user.id
                    )

                elif message.type == MessageType.LEAVE_ROOM:
                    if not message.room:
                        raise ValueError("Room name is required")
                    manager.leave_room(user.id, message.room)
                    response = WebSocketResponse(
                        type=MessageType.INFO,
                        message=f"Left room: {message.room}",
                        room=message.room,
                        data={"rooms": list(manager.get_user_rooms(user.id))},
                    )
                    await manager.send_personal_message(
                        response.model_dump_json(), user.id
                    )

                elif message.type == MessageType.ROOM_MESSAGE:
                    if not message.room:
                        raise ValueError("Room name is required")
                    response = WebSocketResponse(
                        type=MessageType.ROOM_MESSAGE,
                        message=str(message.data),
                        room=message.room,
                        data={"from_user_id": user.id},
                    )
                    await manager.broadcast_to_room(
                        response.model_dump_json(), message.room
                    )

                elif message.type == MessageType.BROADCAST:
                    response = WebSocketResponse(
                        type=MessageType.BROADCAST,
                        message=str(message.data),
                        data={"from_user_id": user.id},
                    )
                    await manager.broadcast_to_all(response.model_dump_json())

                else:
                    error_response = WebSocketResponse(
                        type=MessageType.ERROR,
                        message=f"Unknown message type: {message.type}",
                    )
                    await manager.send_personal_message(
                        error_response.model_dump_json(), user.id
                    )

            except (json.JSONDecodeError, ValueError) as e:
                error_response = WebSocketResponse(
                    type=MessageType.ERROR,
                    message=f"Invalid message format: {str(e)}",
                )
                await manager.send_personal_message(
                    error_response.model_dump_json(), user.id
                )

    except WebSocketDisconnect:
        manager.disconnect(user.id)
