# WebSocket Integration Examples

This document provides examples of how to use the WebSocket feature in the Excludr frontend.

## Basic Setup

The WebSocket connection is automatically established when a user logs in and disconnected when they log out. This is handled in `App.vue`.

## Usage in Components

### 1. Using the WebSocket Store Directly

```vue
<script setup lang="ts">
import { useWebSocketStore } from '@/stores/websocket'
import { storeToRefs } from 'pinia'

const wsStore = useWebSocketStore()
const { isConnected, connectionState, notifications } = storeToRefs(wsStore)

// Send a text message
const sendMessage = () => {
  wsStore.sendText('Hello, server!')
}

// Join a room
const joinProjectRoom = (projectId: number) => {
  wsStore.joinProjectRoom(projectId)
}

// Listen for messages
wsStore.onMessage('info', (response) => {
  console.log('Info message received:', response)
})
</script>
```

### 2. Using the useWebSocket Composable

```vue
<script setup lang="ts">
import { useWebSocket } from '@/composables/useWebSocket'

// This will automatically connect/disconnect based on auth state
const ws = useWebSocket()

// Use all WebSocket store methods
ws.joinRoom('my-room')
ws.sendText('Hello!')
</script>
```

### 3. Listening to Specific Events

```vue
<script setup lang="ts">
import { useWebSocketListener } from '@/composables/useWebSocket'

// Listen for all info messages
useWebSocketListener('info', (response) => {
  console.log('Info:', response.message)
})

// Listen for all messages (wildcard)
useWebSocketListener('*', (response) => {
  console.log('Any message:', response)
})
</script>
```

### 4. Project-Specific WebSocket Integration

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useProjectWebSocket } from '@/composables/useWebSocket'
import { useProjectsStore } from '@/stores/projects'

const props = defineProps<{
  projectId: number
}>()

const projectStore = useProjectsStore()

// Automatically joins project room and listens for project updates
useProjectWebSocket(props.projectId, (response) => {
  if (response.data?.event === 'upload_complete') {
    console.log('Upload completed for project:', props.projectId)
    // The project store will automatically refresh
  }
})
</script>
```

### 5. Manual Notification Display

```vue
<script setup lang="ts">
import { useWebSocketStore } from '@/stores/websocket'

const wsStore = useWebSocketStore()

const showSuccessNotification = () => {
  wsStore.addNotification('Operation completed successfully!', 'success', 5000)
}

const showErrorNotification = () => {
  wsStore.addNotification('An error occurred', 'error', 0) // 0 = no auto-dismiss
}

const showWarningNotification = () => {
  wsStore.addNotification('Warning: Please review', 'warning')
}

const showInfoNotification = () => {
  wsStore.addNotification('New information available', 'info')
}
</script>
```

## Integration with Existing Stores

### Projects Store

The projects store automatically listens for WebSocket notifications and updates projects when:
- File uploads complete
- Projects are updated
- Screening is completed

Example WebSocket message that triggers project update:
```json
{
  "type": "notification",
  "message": "Project upload completed",
  "data": {
    "level": "success",
    "notification": true,
    "project_id": 123,
    "event": "upload_complete"
  }
}
```

### Screening Store

The screening store automatically refreshes stats when:
- New screening decisions are made
- AI screening completes

### Articles Store

The articles store automatically refreshes when:
- Articles are updated
- New articles are uploaded

## WebSocket Event Types

### Standard Events

- `info` - Informational messages
- `error` - Error messages
- `text` - Personal text messages
- `room_message` - Messages to all users in a room
- `broadcast` - Messages to all connected users
- `notification` - Notification messages with level

### Custom Event Handlers

You can create custom event handlers for specific scenarios:

```typescript
// Listen for project-specific events
wsStore.onMessage(`project:${projectId}`, (response) => {
  // Handle project-specific updates
})

// Listen for specific event types in data
wsStore.onMessage('*', (response) => {
  if (response.data?.event === 'upload_complete') {
    // Handle upload completion
  }
})
```

## Notification Levels

- `info` - Blue notification (informational)
- `success` - Green notification (success messages)
- `warning` - Yellow/orange notification (warnings)
- `error` - Red notification (errors)

## Room Management

### Joining Rooms

```typescript
// Join a general room
wsStore.joinRoom('general-chat')

// Join a project-specific room
wsStore.joinProjectRoom(123)
```

### Leaving Rooms

```typescript
// Leave a general room
wsStore.leaveRoom('general-chat')

// Leave a project-specific room
wsStore.leaveProjectRoom(123)
```

### Room Messages

```typescript
// Send a message to all users in a room
wsStore.sendRoomMessage('project_123', 'New screening result available')
```

## Connection State

The WebSocket connection has the following states:

- `disconnected` - Not connected
- `connecting` - Connection in progress
- `connected` - Connected and ready
- `error` - Connection error

```vue
<script setup lang="ts">
import { useWebSocketStore } from '@/stores/websocket'
import { storeToRefs } from 'pinia'

const wsStore = useWebSocketStore()
const { connectionState, isConnected, connectionError } = storeToRefs(wsStore)
</script>

<template>
  <div>
    <p v-if="connectionState === 'connected'">Connected</p>
    <p v-else-if="connectionState === 'connecting'">Connecting...</p>
    <p v-else-if="connectionState === 'error'">Error: {{ connectionError }}</p>
    <p v-else>Disconnected</p>
  </div>
</template>
```

## Auto-Reconnect

The WebSocket connection will automatically attempt to reconnect if disconnected:
- Maximum 5 reconnect attempts
- Exponential backoff (2s, 4s, 6s, 8s, 10s)
- Reconnect attempts reset on successful connection

## Backend Integration

### Sending Notifications from Backend

Backend code can send notifications using the `NotificationService`:

```python
from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel

# Notify a specific user
await NotificationService.notify_user(
    user_id=123,
    message="Your project upload is complete!",
    level=NotificationLevel.SUCCESS,
    data={"project_id": 456, "event": "upload_complete"}
)

# Notify all users in a project room
await NotificationService.notify_room(
    room_name="project_456",
    message="New screening result available",
    level=NotificationLevel.INFO,
    data={"project_id": 456, "event": "screening_complete"}
)
```

## Best Practices

1. **Use composables for component-level integration** - Use `useWebSocket`, `useWebSocketListener`, or `useProjectWebSocket`
2. **Clean up listeners** - The composables handle cleanup automatically in `onUnmounted`
3. **Use appropriate notification levels** - Choose the right level (info, success, warning, error)
4. **Join project rooms when viewing projects** - Use `joinProjectRoom` to receive project-specific updates
5. **Handle connection states** - Display appropriate UI based on `connectionState`
6. **Use the wildcard listener sparingly** - Listening to all messages (`*`) can impact performance
7. **Leverage store integrations** - The projects, screening, and articles stores already handle most common updates

## Troubleshooting

### WebSocket not connecting

1. Check if the user is authenticated
2. Verify the JWT token is valid
3. Check browser console for connection errors
4. Ensure WebSocket endpoint is accessible

### Notifications not appearing

1. Verify `ToastContainer` is included in `App.vue`
2. Check if notifications are being added: `wsStore.notifications`
3. Ensure notification has a valid level

### Missing updates

1. Verify you've joined the appropriate room
2. Check if the event handler is registered
3. Ensure the backend is sending notifications with the correct format
