<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useWebSocketStore } from '@/stores/websocket'
import { useWebSocketListener } from '@/composables/useWebSocket'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'

const wsStore = useWebSocketStore()
const { isConnected, connectionState, userRooms, notifications } = storeToRefs(wsStore)

const messageText = ref('')
const roomName = ref('')
const messageLog = ref<Array<{ time: string; message: string }>>([])

// Listen for all incoming messages
useWebSocketListener('*', (response) => {
  const time = new Date().toLocaleTimeString()
  messageLog.value.unshift({
    time,
    message: `[${response.type}] ${response.message}`,
  })

  // Keep only last 20 messages
  if (messageLog.value.length > 20) {
    messageLog.value = messageLog.value.slice(0, 20)
  }
})

const sendTextMessage = () => {
  if (messageText.value.trim()) {
    wsStore.sendText(messageText.value)
    messageText.value = ''
  }
}

const joinRoom = () => {
  if (roomName.value.trim()) {
    wsStore.joinRoom(roomName.value)
  }
}

const leaveRoom = (room: string) => {
  wsStore.leaveRoom(room)
}

const testNotifications = () => {
  wsStore.addNotification('This is an info notification', 'info')
  setTimeout(() => {
    wsStore.addNotification('This is a success notification', 'success')
  }, 500)
  setTimeout(() => {
    wsStore.addNotification('This is a warning notification', 'warning')
  }, 1000)
  setTimeout(() => {
    wsStore.addNotification('This is an error notification', 'error')
  }, 1500)
}

const getConnectionStateBadge = () => {
  switch (connectionState.value) {
    case 'connected':
      return 'default' // Green/primary for connected
    case 'connecting':
      return 'secondary' // Gray for connecting
    case 'error':
      return 'destructive' // Red for error
    default:
      return 'outline' // Outline for disconnected
  }
}
</script>

<template>
  <div class="container mx-auto p-6 max-w-4xl">
    <h1 class="text-3xl font-bold mb-6">WebSocket Demo</h1>

    <!-- Connection Status -->
    <Card class="p-6 mb-6">
      <h2 class="text-xl font-semibold mb-4">Connection Status</h2>
      <div class="flex items-center gap-4">
        <Badge :variant="getConnectionStateBadge()">
          {{ connectionState }}
        </Badge>
        <span v-if="isConnected" class="text-sm text-gray-600">
          Connected and ready to send/receive messages
        </span>
        <span v-else class="text-sm text-gray-600">
          Not connected to WebSocket server
        </span>
      </div>
    </Card>

    <!-- Current Rooms -->
    <Card class="p-6 mb-6">
      <h2 class="text-xl font-semibold mb-4">Current Rooms</h2>
      <div v-if="userRooms.length > 0" class="flex flex-wrap gap-2">
        <div
          v-for="room in userRooms"
          :key="room"
          class="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-1"
        >
          <span class="text-sm font-medium">{{ room }}</span>
          <button
            @click="leaveRoom(room)"
            class="text-blue-600 hover:text-blue-800 text-sm"
          >
            ✕
          </button>
        </div>
      </div>
      <p v-else class="text-sm text-gray-500">Not in any rooms yet</p>
    </Card>

    <!-- Send Message -->
    <Card class="p-6 mb-6">
      <h2 class="text-xl font-semibold mb-4">Send Message</h2>
      <div class="flex gap-2">
        <Input
          v-model="messageText"
          placeholder="Enter message..."
          @keyup.enter="sendTextMessage"
          :disabled="!isConnected"
        />
        <Button @click="sendTextMessage" :disabled="!isConnected">Send</Button>
      </div>
    </Card>

    <!-- Join Room -->
    <Card class="p-6 mb-6">
      <h2 class="text-xl font-semibold mb-4">Join Room</h2>
      <div class="flex gap-2">
        <Input
          v-model="roomName"
          placeholder="Enter room name..."
          @keyup.enter="joinRoom"
          :disabled="!isConnected"
        />
        <Button @click="joinRoom" :disabled="!isConnected">Join</Button>
      </div>
    </Card>

    <!-- Test Notifications -->
    <Card class="p-6 mb-6">
      <h2 class="text-xl font-semibold mb-4">Test Notifications</h2>
      <Button @click="testNotifications">Show All Notification Types</Button>
    </Card>

    <!-- Message Log -->
    <Card class="p-6">
      <h2 class="text-xl font-semibold mb-4">Message Log</h2>
      <div class="bg-gray-50 rounded-lg p-4 max-h-96 overflow-y-auto">
        <div v-if="messageLog.length > 0" class="space-y-2">
          <div
            v-for="(msg, index) in messageLog"
            :key="index"
            class="text-sm font-mono border-b border-gray-200 pb-2"
          >
            <span class="text-gray-500">[{{ msg.time }}]</span>
            {{ msg.message }}
          </div>
        </div>
        <p v-else class="text-sm text-gray-500">No messages yet</p>
      </div>
    </Card>
  </div>
</template>
