# WebSocket Feature Documentation

This document describes the complete WebSocket implementation for real-time communication between the Excludr frontend and backend.

## Overview

The WebSocket feature enables real-time, bidirectional communication between the frontend and backend. It's used for:

- Real-time notifications (upload completion, processing updates, etc.)
- Live updates to projects, articles, and screening data
- Room-based messaging for project collaboration
- Connection state management with auto-reconnect

## Architecture

### Components

1. **WebSocket Store** (`/frontend/src/stores/websocket.ts`)
   - Core WebSocket connection management
   - Auto-reconnect logic
   - Message sending/receiving
   - Notification queue management
   - Event handler registration

2. **Toast Notifications** (`/frontend/src/components/ui/Toast.vue`, `ToastContainer.vue`)
   - Visual notification display
   - Supports 4 levels: info, success, warning, error
   - Auto-dismiss with configurable duration
   - Smooth animations

3. **Composables** (`/frontend/src/composables/useWebSocket.ts`)
   - `useWebSocket()` - Basic WebSocket integration
   - `useWebSocketListener()` - Event-specific listeners
   - `useProjectWebSocket()` - Project-specific integration

4. **Store Integrations**
   - Projects Store - Auto-updates on upload completion, project changes
   - Screening Store - Auto-updates on screening decisions
   - Articles Store - Auto-updates on article changes

### File Structure

```
frontend/src/
├── components/
│   ├── ui/
│   │   ├── Toast.vue                    # Toast notification component
│   │   └── ToastContainer.vue           # Container for multiple toasts
│   └── examples/
│       └── WebSocketDemo.vue            # Demo component
├── composables/
│   └── useWebSocket.ts                  # WebSocket composables
├── stores/
│   ├── websocket.ts                     # Main WebSocket store
│   ├── websocket.examples.md            # Usage examples
│   ├── projects.ts                      # Updated with WS integration
│   ├── screening.ts                     # Updated with WS integration
│   └── articles.ts                      # Updated with WS integration
├── types/
│   └── index.ts                         # WebSocket type definitions
├── App.vue                              # Updated to include ToastContainer
└── WEBSOCKET_README.md                  # This file
```

## Features

### 1. Connection Management

- Automatic connection on login
- Automatic disconnection on logout
- Auto-reconnect with exponential backoff
- Connection state tracking

```typescript
const wsStore = useWebSocketStore()

// Connection states: 'disconnected', 'connecting', 'connected', 'error'
console.log(wsStore.connectionState)
console.log(wsStore.isConnected)
```

### 2. Room Management

Users can join/leave rooms for targeted messaging:

```typescript
// Join a room
wsStore.joinRoom('project_123')

// Leave a room
wsStore.leaveRoom('project_123')

// Convenience methods for projects
wsStore.joinProjectRoom(123)
wsStore.leaveProjectRoom(123)
```

### 3. Message Handling

Send and receive different types of messages:

```typescript
// Send personal text message
wsStore.sendText('Hello!')

// Send message to room
wsStore.sendRoomMessage('project_123', 'Update available')

// Broadcast to all users
wsStore.broadcast('System maintenance in 5 minutes')
```

### 4. Notification System

Display toast notifications with different levels:

```typescript
// Add notifications programmatically
wsStore.addNotification('Success!', 'success', 5000) // 5 second duration
wsStore.addNotification('Warning!', 'warning')
wsStore.addNotification('Error!', 'error', 0) // No auto-dismiss

// Remove specific notification
wsStore.removeNotification(notificationId)

// Clear all notifications
wsStore.clearNotifications()
```

### 5. Event Handlers

Register handlers for specific event types:

```typescript
// Listen for info messages
const unsubscribe = wsStore.onMessage('info', (response) => {
  console.log('Info:', response.message)
})

// Listen for all messages
wsStore.onMessage('*', (response) => {
  console.log('Message:', response)
})

// Listen for project-specific messages
wsStore.onMessage('project:123', (response) => {
  console.log('Project 123 update:', response)
})

// Clean up
unsubscribe()
```

### 6. Auto-Reconnect

Automatic reconnection with smart retry logic:

- Maximum 5 reconnect attempts
- Exponential backoff: 2s, 4s, 6s, 8s, 10s
- Resets on successful connection
- Shows error notification after max attempts

## Usage Examples

### Basic Component Integration

```vue
<script setup lang="ts">
import { useWebSocket } from '@/composables/useWebSocket'
import { storeToRefs } from 'pinia'

const ws = useWebSocket()
const { isConnected, notifications } = storeToRefs(ws)

const handleClick = () => {
  ws.addNotification('Button clicked!', 'success')
}
</script>

<template>
  <div>
    <p v-if="isConnected">Connected</p>
    <button @click="handleClick">Test Notification</button>
  </div>
</template>
```

### Project-Specific Integration

```vue
<script setup lang="ts">
import { useProjectWebSocket } from '@/composables/useWebSocket'

const props = defineProps<{ projectId: number }>()

// Automatically joins project room and listens for updates
useProjectWebSocket(props.projectId, (response) => {
  if (response.data?.event === 'upload_complete') {
    console.log('Upload completed!')
  }
})
</script>
```

### Listening to Specific Events

```vue
<script setup lang="ts">
import { useWebSocketListener } from '@/composables/useWebSocket'

// Listen for upload completion events
useWebSocketListener('*', (response) => {
  if (response.data?.event === 'upload_complete') {
    console.log('Upload done for project:', response.data.project_id)
  }
})
</script>
```

## Store Integration

### Projects Store

Automatically updates when:
- File uploads complete
- Projects are updated
- Screening is completed

```typescript
// Backend sends notification like:
{
  "type": "info",
  "message": "Upload completed",
  "data": {
    "level": "success",
    "notification": true,
    "project_id": 123,
    "event": "upload_complete"
  }
}

// Projects store automatically:
// 1. Shows toast notification
// 2. Refreshes the project data
```

### Screening Store

Automatically updates statistics when:
- New screening decisions are made
- AI screening completes

### Articles Store

Automatically refreshes articles list when:
- Articles are updated
- New uploads complete

## Backend Integration

The backend uses the `NotificationService` to send messages:

```python
from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel

# Notify specific user
await NotificationService.notify_user(
    user_id=123,
    message="Your upload is complete!",
    level=NotificationLevel.SUCCESS,
    data={"project_id": 456, "event": "upload_complete"}
)

# Notify room
await NotificationService.notify_room(
    room_name="project_456",
    message="New screening results",
    level=NotificationLevel.INFO,
    data={"project_id": 456, "event": "screening_complete"}
)

# Broadcast to all
await NotificationService.broadcast(
    message="System maintenance starting",
    level=NotificationLevel.WARNING
)
```

## Message Format

### Client to Server

```typescript
{
  type: 'text' | 'join_room' | 'leave_room' | 'room_message' | 'broadcast',
  data: any,
  room?: string  // Required for room operations
}
```

### Server to Client

```typescript
{
  type: 'info' | 'error' | 'text' | 'room_message' | 'broadcast' | 'notification',
  message: string,
  data?: {
    level?: 'info' | 'success' | 'warning' | 'error',
    notification?: boolean,
    project_id?: number,
    user_id?: number,
    rooms?: string[],
    event?: string,
    // ... any custom data
  },
  room?: string
}
```

## Notification Levels

| Level   | Color  | Icon | Use Case                          |
|---------|--------|------|-----------------------------------|
| info    | Blue   | ℹ    | General information               |
| success | Green  | ✓    | Successful operations             |
| warning | Yellow | ⚠    | Warnings, non-critical issues     |
| error   | Red    | ✕    | Errors, failed operations         |

## Best Practices

1. **Use Composables** - Prefer `useWebSocket()`, `useWebSocketListener()`, or `useProjectWebSocket()` for component integration
2. **Clean Up Handlers** - Always unsubscribe from event handlers (composables do this automatically)
3. **Appropriate Levels** - Use correct notification levels for better UX
4. **Join Project Rooms** - Join project-specific rooms when viewing project details
5. **Handle Connection States** - Show appropriate UI based on connection state
6. **Leverage Store Integration** - Most common updates are already handled by store integrations
7. **Wildcard Listeners** - Use `'*'` listener sparingly, prefer specific event types

## Testing

### Demo Component

A demo component is available at `/frontend/src/components/examples/WebSocketDemo.vue` that demonstrates:

- Connection status
- Room management
- Message sending
- Notification display
- Event logging

### Manual Testing

1. Login to the application
2. Open browser DevTools console
3. Check for "WebSocket connected" message
4. Use the demo component to test features
5. Check Network tab for WebSocket frames

### Integration Testing

The backend has comprehensive tests at:
- `/tests/features/websocket/test_websocket.py`
- `/tests/features/websocket/test_notification_service.py`

## Troubleshooting

### WebSocket Won't Connect

**Symptoms:** Connection state stuck on "connecting" or "error"

**Solutions:**
1. Check if user is authenticated
2. Verify JWT token is valid (check localStorage)
3. Check browser console for errors
4. Verify backend WebSocket endpoint is running
5. Check for CORS issues

### Notifications Not Showing

**Symptoms:** Messages received but no toast appears

**Solutions:**
1. Verify `ToastContainer` is in `App.vue`
2. Check `wsStore.notifications` array
3. Ensure notification has valid level
4. Check if notification was auto-dismissed

### Missing Real-time Updates

**Symptoms:** WebSocket connected but updates not reflected

**Solutions:**
1. Verify you've joined the appropriate room
2. Check if event handler is registered
3. Inspect WebSocket frames in DevTools
4. Verify backend is sending correct message format
5. Check store integration is working

### Auto-Reconnect Not Working

**Symptoms:** Connection lost and doesn't reconnect

**Solutions:**
1. Check if max attempts (5) exceeded
2. Verify token is still valid
3. Check browser console for reconnect logs
4. Manually call `wsStore.connect(token)` to reset

## Performance Considerations

1. **Notification Limit** - Toast notifications auto-remove after duration to prevent memory buildup
2. **Message Log Limit** - Demo component limits to 20 messages
3. **Handler Cleanup** - Always clean up event handlers to prevent memory leaks
4. **Wildcard Listeners** - Use specific event types when possible for better performance

## Security

1. **JWT Authentication** - All WebSocket connections require valid JWT token
2. **Token in Query** - Token passed as query parameter for WebSocket handshake
3. **Room Authorization** - Backend validates room access (future enhancement)
4. **Message Validation** - All messages validated with Pydantic schemas

## Future Enhancements

- Typing indicators for collaborative screening
- User presence (online/offline status)
- Unread message counts
- Message persistence and history
- File transfer over WebSocket
- Voice/video call signaling
- Advanced room permissions

## Additional Resources

- [WebSocket Store Examples](./src/stores/websocket.examples.md) - Detailed usage examples
- [Demo Component](./src/components/examples/WebSocketDemo.vue) - Interactive demo
- [Backend WebSocket Docs](../app/features/websocket/examples.py) - Backend integration examples
