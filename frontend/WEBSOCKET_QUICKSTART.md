# WebSocket Quick Start Guide

Get up and running with WebSocket real-time features in 5 minutes.

## Setup (Already Done)

The WebSocket feature is already configured and active in the application. When you login, the WebSocket connection is automatically established.

## Quick Examples

### 1. Show a Notification

```typescript
import { useWebSocketStore } from '@/stores/websocket'

const wsStore = useWebSocketStore()

// Show success notification
wsStore.addNotification('Upload completed!', 'success')

// Show error notification
wsStore.addNotification('Upload failed', 'error')
```

### 2. Listen for Real-time Updates (in any component)

```vue
<script setup lang="ts">
import { useWebSocketListener } from '@/composables/useWebSocket'

// Listen for all WebSocket messages
useWebSocketListener('*', (response) => {
  console.log('Received:', response.message)

  // Check for specific events
  if (response.data?.event === 'upload_complete') {
    console.log('Upload done for project:', response.data.project_id)
  }
})
</script>
```

### 3. Project-Specific Updates

```vue
<script setup lang="ts">
import { useProjectWebSocket } from '@/composables/useWebSocket'

const props = defineProps<{ projectId: number }>()

// Auto-joins project room and listens for project updates
useProjectWebSocket(props.projectId, (response) => {
  console.log('Project update:', response)
})
</script>
```

### 4. Check Connection Status

```vue
<script setup lang="ts">
import { useWebSocketStore } from '@/stores/websocket'
import { storeToRefs } from 'pinia'

const wsStore = useWebSocketStore()
const { isConnected, connectionState } = storeToRefs(wsStore)
</script>

<template>
  <div v-if="isConnected">
    ✓ Connected
  </div>
  <div v-else>
    ⚠ Disconnected ({{ connectionState }})
  </div>
</template>
```

### 5. Join/Leave Rooms

```typescript
const wsStore = useWebSocketStore()

// Join a room
wsStore.joinRoom('project_123')

// Leave a room
wsStore.leaveRoom('project_123')

// Or use convenience methods
wsStore.joinProjectRoom(123)
wsStore.leaveProjectRoom(123)
```

## Automatic Features (No Code Needed)

The following features work automatically without any code:

1. **Real-time Notifications** - All backend notifications appear as toasts
2. **Project Updates** - Projects automatically refresh when uploads complete
3. **Article Updates** - Article lists refresh when new articles are added
4. **Screening Stats** - Screening statistics update in real-time
5. **Auto-Reconnect** - Connection automatically restores if lost

## Testing Your Integration

### Option 1: Use the Demo Component

Add this to your router (for testing):

```typescript
{
  path: '/websocket-demo',
  component: () => import('@/components/examples/WebSocketDemo.vue'),
}
```

Then visit `/websocket-demo` to test all features interactively.

### Option 2: Test from Backend

From your backend code, send a test notification:

```python
from app.features.websocket.services import NotificationService
from app.features.websocket.schemas import NotificationLevel

await NotificationService.notify_user(
    user_id=1,  # Your user ID
    message="Test notification from backend!",
    level=NotificationLevel.SUCCESS,
    data={"test": True}
)
```

### Option 3: Test from Browser Console

```javascript
// Get the WebSocket store
const ws = window.$pinia.state.value.websocket

// Send a test message
ws.sendText('Hello from console!')

// Show a notification
ws.addNotification('Console test!', 'info')

// Check connection
console.log('Connected:', ws.isConnected)
console.log('Rooms:', ws.userRooms)
```

## Common Use Cases

### Use Case 1: Upload Progress Notification

When a file upload completes in the background, show a notification:

**Backend** (already implemented in tasks):
```python
await NotificationService.notify_user(
    user_id=user_id,
    message=f"Upload completed: {project.name}",
    level=NotificationLevel.SUCCESS,
    data={"project_id": project.id, "event": "upload_complete"}
)
```

**Frontend** (automatic):
- Notification appears automatically
- Projects store refreshes the project
- Articles store refreshes if viewing that project

### Use Case 2: Screening Progress

Show real-time screening progress:

**Frontend**:
```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useProjectWebSocket } from '@/composables/useWebSocket'

const props = defineProps<{ projectId: number }>()
const screeningProgress = ref(0)

useProjectWebSocket(props.projectId, (response) => {
  if (response.data?.event === 'screening_progress') {
    screeningProgress.value = response.data.progress
  }
})
</script>

<template>
  <div>Progress: {{ screeningProgress }}%</div>
</template>
```

**Backend**:
```python
await NotificationService.notify_room(
    room_name=f"project_{project_id}",
    message="Screening in progress...",
    level=NotificationLevel.INFO,
    data={
        "project_id": project_id,
        "event": "screening_progress",
        "progress": 45
    }
)
```

### Use Case 3: Collaborative Notifications

Notify all users viewing a project:

```python
# When user A makes a screening decision, notify others in the project
await NotificationService.notify_room(
    room_name=f"project_{project_id}",
    message=f"New screening decision by {user.name}",
    level=NotificationLevel.INFO,
    data={
        "project_id": project_id,
        "event": "screening_decision",
        "article_id": article_id
    }
)
```

## Notification Levels Guide

| Level | When to Use | Color |
|-------|-------------|-------|
| `info` | General updates, progress | Blue |
| `success` | Completed tasks, confirmations | Green |
| `warning` | Non-critical issues, alerts | Yellow |
| `error` | Failures, errors | Red |

## Tips

1. **Always use composables** - `useWebSocket()`, `useWebSocketListener()`, `useProjectWebSocket()`
2. **Composables auto-cleanup** - No need to manually unsubscribe
3. **Check connection state** - Use `isConnected` before sending messages
4. **Use appropriate notification levels** - Helps users understand urgency
5. **Join project rooms** - Get project-specific real-time updates
6. **Leverage automatic features** - Projects/articles/screening already update automatically

## Troubleshooting

**Not connected?**
- Check if logged in
- Check browser console for errors
- Verify backend is running

**No notifications showing?**
- `ToastContainer` is already in `App.vue`
- Check notification level is valid
- Try manual: `wsStore.addNotification('test', 'info')`

**Updates not working?**
- Join the appropriate room first
- Check event handler is registered
- Verify backend is sending correct format

## Next Steps

- Read [Full Documentation](./WEBSOCKET_README.md)
- See [Detailed Examples](./src/stores/websocket.examples.md)
- Try [Demo Component](./src/components/examples/WebSocketDemo.vue)

## Need Help?

Check the comprehensive documentation:
- `WEBSOCKET_README.md` - Complete feature documentation
- `src/stores/websocket.examples.md` - Detailed code examples
- `src/components/examples/WebSocketDemo.vue` - Interactive demo
