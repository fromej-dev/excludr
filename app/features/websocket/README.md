# WebSocket Feature with Room Management

This feature provides real-time WebSocket communication with JWT authentication and room management capabilities. It includes a notification service for sending backend-to-frontend messages.

## Features

- **JWT Authentication**: Secure WebSocket connections using existing JWT tokens
- **Room Management**: Users can join/leave rooms for group messaging
- **Personal Rooms**: Each user is automatically added to a personal room (`user_{user_id}`)
- **Notification Service**: Easy-to-use service for sending notifications from anywhere in your backend
- **Multiple Message Types**: Support for personal messages, room messages, and broadcasts

## Quick Start

### Connecting to WebSocket

```javascript
// Frontend JavaScript example
const token = "your_jwt_token_here";
const ws = new WebSocket(`ws://localhost:8000/api/v1/ws?token=${token}`);

ws.onopen = () => {
  console.log('Connected to WebSocket');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);

  // Handle different message types
  if (data.data?.notification) {
    // This is a notification from the backend
    showNotification(data.message, data.data.level);
  }
};
```

### Message Format

All messages are JSON objects with the following structure:

```json
{
  "type": "text|join_room|leave_room|room_message|broadcast",
  "data": "message content or data",
  "room": "room_name (optional, required for room operations)"
}
```

### Response Format

All responses from the server follow this structure:

```json
{
  "type": "info|error|text|room_message|broadcast|notification",
  "message": "The message content",
  "data": {
    "level": "info|success|warning|error",
    "notification": true,
    // ... additional data
  },
  "room": "room_name (if applicable)"
}
```

## Using the Notification Service

The `NotificationService` allows you to send real-time notifications to users from anywhere in your backend code.

### Basic Usage

```python
from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel

# Notify a specific user
await NotificationService.notify_user(
    user_id=123,
    message="Your project upload is complete!",
    level=NotificationLevel.SUCCESS,
    data={"project_id": 456}
)
```

### Notification Levels

- `NotificationLevel.INFO` - Informational messages
- `NotificationLevel.SUCCESS` - Success messages (green)
- `NotificationLevel.WARNING` - Warning messages (yellow/orange)
- `NotificationLevel.ERROR` - Error messages (red)

### Available Methods

#### 1. Notify a Specific User

```python
result = await NotificationService.notify_user(
    user_id=user.id,
    message="Processing complete!",
    level=NotificationLevel.SUCCESS,
    data={"custom_field": "value"}
)
# Returns True if user is connected, False otherwise
```

#### 2. Notify All Users in a Room

```python
count = await NotificationService.notify_room(
    room_name="project_123",
    message="New screening result available",
    level=NotificationLevel.INFO
)
# Returns the number of users notified
```

#### 3. Broadcast to All Connected Users

```python
count = await NotificationService.broadcast(
    message="System maintenance in 5 minutes",
    level=NotificationLevel.WARNING
)
# Returns the number of users notified
```

#### 4. Notify User's Personal Room

```python
result = await NotificationService.notify_user_in_room(
    user_id=user.id,
    message="You have a new message",
    level=NotificationLevel.INFO
)
```

#### 5. Check Connection Status

```python
# Check if a user is connected
is_online = NotificationService.is_user_connected(user_id)

# Get all connected user IDs
connected_users = NotificationService.get_connected_users()

# Get all users in a specific room
room_members = NotificationService.get_room_members("project_123")
```

## Usage Examples

### Example 1: Notify After File Upload

```python
from fastapi import APIRouter, UploadFile
from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel

@router.post("/projects/{project_id}/upload")
async def upload_file(
    project_id: int,
    file: UploadFile,
    current_user: User = Depends(get_current_user)
):
    # Process file upload...
    process_upload(file, project_id)

    # Notify user
    await NotificationService.notify_user(
        user_id=current_user.id,
        message=f"File '{file.filename}' uploaded successfully!",
        level=NotificationLevel.SUCCESS,
        data={"project_id": project_id, "filename": file.filename}
    )

    return {"status": "success"}
```

### Example 2: Notify Project Collaborators

```python
async def notify_project_update(project_id: int, update_message: str):
    """Notify all users working on a project."""
    room_name = f"project_{project_id}"

    count = await NotificationService.notify_room(
        room_name=room_name,
        message=update_message,
        level=NotificationLevel.INFO,
        data={"project_id": project_id, "action": "project_update"}
    )

    print(f"Notified {count} users in project {project_id}")
```

### Example 3: Background Task Notifications

```python
# In a Celery task or Prefect flow
from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel
import asyncio

def process_data_task(user_id: int, data_id: int):
    try:
        # Process data...
        result = process_data(data_id)

        # Notify success
        asyncio.run(NotificationService.notify_user(
            user_id=user_id,
            message="Data processing complete!",
            level=NotificationLevel.SUCCESS,
            data={"data_id": data_id, "result": result}
        ))
    except Exception as e:
        # Notify error
        asyncio.run(NotificationService.notify_user(
            user_id=user_id,
            message=f"Processing failed: {str(e)}",
            level=NotificationLevel.ERROR,
            data={"data_id": data_id, "error": str(e)}
        ))
```

### Example 4: Conditional Notifications

```python
async def notify_if_online(user_id: int, message: str):
    """Only notify if user is currently connected."""
    if NotificationService.is_user_connected(user_id):
        await NotificationService.notify_user(
            user_id=user_id,
            message=message,
            level=NotificationLevel.INFO
        )
        return True
    else:
        # Save to database for later display
        save_notification_to_db(user_id, message)
        return False
```

## Room Management

### Joining a Room

```javascript
// Frontend
ws.send(JSON.stringify({
  type: 'join_room',
  room: 'project_123'
}));
```

### Leaving a Room

```javascript
// Frontend
ws.send(JSON.stringify({
  type: 'leave_room',
  room: 'project_123'
}));
```

### Sending Message to Room

```javascript
// Frontend
ws.send(JSON.stringify({
  type: 'room_message',
  room: 'project_123',
  data: 'Hello everyone in the project!'
}));
```

## Frontend Integration Example

```javascript
class WebSocketManager {
  constructor(token) {
    this.token = token;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }

  connect() {
    this.ws = new WebSocket(`ws://localhost:8000/api/v1/ws?token=${this.token}`);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.reconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  handleMessage(data) {
    // Handle notifications
    if (data.data?.notification) {
      this.showNotification(data.message, data.data.level);
    }

    // Handle other message types
    switch (data.type) {
      case 'info':
        console.log('Info:', data.message);
        break;
      case 'error':
        console.error('Error:', data.message);
        break;
      case 'room_message':
        this.handleRoomMessage(data);
        break;
      case 'broadcast':
        this.handleBroadcast(data);
        break;
    }
  }

  showNotification(message, level) {
    // Integrate with your notification UI library
    // Examples: toast, snackbar, etc.
    console.log(`[${level}] ${message}`);
  }

  joinRoom(roomName) {
    this.send({
      type: 'join_room',
      room: roomName
    });
  }

  leaveRoom(roomName) {
    this.send({
      type: 'leave_room',
      room: roomName
    });
  }

  send(message) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  reconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Usage
const wsManager = new WebSocketManager(yourJwtToken);
wsManager.connect();
```

## Testing

The feature includes comprehensive tests. Run them with:

```bash
pytest tests/features/websocket/ -v
```

## Architecture

- **`manager.py`**: ConnectionManager class for managing WebSocket connections and rooms
- **`routers.py`**: WebSocket endpoint with JWT authentication
- **`services.py`**: NotificationService for backend-to-frontend messaging
- **`schemas.py`**: Pydantic models for messages and notifications
- **`examples.py`**: Example code for common use cases

## Security

- All WebSocket connections require valid JWT authentication
- Tokens are validated using the same logic as HTTP endpoints
- Invalid tokens result in connection rejection (HTTP 403)

## Best Practices

1. **Always check connection status** before sending critical notifications
2. **Use appropriate notification levels** to help users distinguish message importance
3. **Include actionable data** in notifications (IDs, URLs, etc.)
4. **Handle disconnections gracefully** on the frontend with reconnection logic
5. **Use rooms** for group notifications instead of sending individual messages
6. **Clean up subscriptions** when users navigate away from features

## See Also

- Check `examples.py` for more detailed usage examples
- See tests in `tests/features/websocket/` for comprehensive examples
