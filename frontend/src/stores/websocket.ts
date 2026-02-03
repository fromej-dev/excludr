import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  WebSocketMessage,
  WebSocketResponse,
  MessageType,
  NotificationLevel,
  ToastNotification,
} from '@/types'

// Generate unique notification ID
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

export const useWebSocketStore = defineStore('websocket', () => {
  // State
  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const isConnecting = ref(false)
  const connectionError = ref<string | null>(null)
  const notifications = ref<ToastNotification[]>([])
  const userRooms = ref<string[]>([])
  const messageHandlers = ref<Map<string, Set<(data: any) => void>>>(new Map())

  // Auto-reconnect settings
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 5
  const reconnectDelay = 2000 // 2 seconds
  const reconnectTimer = ref<number | null>(null)

  // Computed
  const connectionState = computed(() => {
    if (isConnected.value) return 'connected'
    if (isConnecting.value) return 'connecting'
    if (connectionError.value) return 'error'
    return 'disconnected'
  })

  // Get WebSocket URL
  const getWebSocketUrl = (token: string): string => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    return `${protocol}//${host}/api/v1/ws?token=${token}`
  }

  // Add notification
  const addNotification = (
    message: string,
    level: NotificationLevel = 'info',
    duration: number = 5000
  ) => {
    const notification: ToastNotification = {
      id: generateId(),
      message,
      level,
      duration,
      timestamp: Date.now(),
    }

    notifications.value.push(notification)

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        removeNotification(notification.id)
      }, duration)
    }

    return notification.id
  }

  // Remove notification
  const removeNotification = (id: string) => {
    const index = notifications.value.findIndex((n) => n.id === id)
    if (index !== -1) {
      notifications.value.splice(index, 1)
    }
  }

  // Clear all notifications
  const clearNotifications = () => {
    notifications.value = []
  }

  // Register message handler for specific event types
  const onMessage = (eventType: string, handler: (data: any) => void) => {
    if (!messageHandlers.value.has(eventType)) {
      messageHandlers.value.set(eventType, new Set())
    }
    messageHandlers.value.get(eventType)!.add(handler)

    // Return unsubscribe function
    return () => {
      const handlers = messageHandlers.value.get(eventType)
      if (handlers) {
        handlers.delete(handler)
        if (handlers.size === 0) {
          messageHandlers.value.delete(eventType)
        }
      }
    }
  }

  // Trigger message handlers
  const triggerHandlers = (eventType: string, data: any) => {
    const handlers = messageHandlers.value.get(eventType)
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data)
        } catch (error) {
          console.error(`Error in message handler for ${eventType}:`, error)
        }
      })
    }
  }

  // Handle incoming WebSocket messages
  const handleMessage = (event: MessageEvent) => {
    try {
      const response: WebSocketResponse = JSON.parse(event.data)

      // Handle notifications
      if (response.data?.notification) {
        const level = (response.data.level as NotificationLevel) || 'info'
        addNotification(response.message, level)
      }

      // Update user rooms if provided
      if (response.data?.rooms) {
        userRooms.value = response.data.rooms
      }

      // Trigger specific handlers based on message type
      triggerHandlers(response.type, response)

      // Trigger handlers based on data attributes
      if (response.data?.project_id) {
        triggerHandlers(`project:${response.data.project_id}`, response)
      }

      // Trigger general message handler
      triggerHandlers('*', response)
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error)
    }
  }

  // Connect to WebSocket
  const connect = (token: string) => {
    if (isConnected.value || isConnecting.value) {
      console.warn('WebSocket is already connected or connecting')
      return
    }

    isConnecting.value = true
    connectionError.value = null

    try {
      const url = getWebSocketUrl(token)
      ws.value = new WebSocket(url)

      ws.value.onopen = () => {
        console.log('WebSocket connected')
        isConnected.value = true
        isConnecting.value = false
        reconnectAttempts.value = 0
        connectionError.value = null

        // Clear any pending reconnect timer
        if (reconnectTimer.value) {
          clearTimeout(reconnectTimer.value)
          reconnectTimer.value = null
        }
      }

      ws.value.onmessage = handleMessage

      ws.value.onerror = (error) => {
        console.error('WebSocket error:', error)
        connectionError.value = 'WebSocket connection error'
      }

      ws.value.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason)
        isConnected.value = false
        isConnecting.value = false

        // Attempt reconnect if not a normal closure and haven't exceeded max attempts
        if (event.code !== 1000 && reconnectAttempts.value < maxReconnectAttempts) {
          scheduleReconnect(token)
        } else if (reconnectAttempts.value >= maxReconnectAttempts) {
          connectionError.value = 'Failed to reconnect after multiple attempts'
          addNotification('WebSocket connection lost', 'error')
        }
      }
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
      isConnecting.value = false
      connectionError.value = 'Failed to create connection'
    }
  }

  // Schedule reconnect attempt
  const scheduleReconnect = (token: string) => {
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
    }

    reconnectAttempts.value++
    const delay = reconnectDelay * reconnectAttempts.value

    console.log(
      `Scheduling reconnect attempt ${reconnectAttempts.value}/${maxReconnectAttempts} in ${delay}ms`
    )

    reconnectTimer.value = window.setTimeout(() => {
      console.log(`Attempting to reconnect (${reconnectAttempts.value}/${maxReconnectAttempts})`)
      connect(token)
    }, delay)
  }

  // Disconnect from WebSocket
  const disconnect = () => {
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value)
      reconnectTimer.value = null
    }

    reconnectAttempts.value = maxReconnectAttempts // Prevent auto-reconnect

    if (ws.value) {
      ws.value.close(1000, 'User disconnected')
      ws.value = null
    }

    isConnected.value = false
    isConnecting.value = false
    userRooms.value = []
    messageHandlers.value.clear()
  }

  // Send message
  const sendMessage = (message: WebSocketMessage) => {
    if (!isConnected.value || !ws.value) {
      console.error('WebSocket is not connected')
      addNotification('Not connected to server', 'error')
      return false
    }

    try {
      ws.value.send(JSON.stringify(message))
      return true
    } catch (error) {
      console.error('Failed to send message:', error)
      addNotification('Failed to send message', 'error')
      return false
    }
  }

  // Join room
  const joinRoom = (roomName: string) => {
    return sendMessage({
      type: 'join_room',
      data: roomName,
      room: roomName,
    })
  }

  // Leave room
  const leaveRoom = (roomName: string) => {
    return sendMessage({
      type: 'leave_room',
      data: roomName,
      room: roomName,
    })
  }

  // Send text message
  const sendText = (text: string) => {
    return sendMessage({
      type: 'text',
      data: text,
    })
  }

  // Send room message
  const sendRoomMessage = (roomName: string, message: string) => {
    return sendMessage({
      type: 'room_message',
      data: message,
      room: roomName,
    })
  }

  // Broadcast message
  const broadcast = (message: string) => {
    return sendMessage({
      type: 'broadcast',
      data: message,
    })
  }

  // Join project room (convenience method)
  const joinProjectRoom = (projectId: number) => {
    return joinRoom(`project_${projectId}`)
  }

  // Leave project room (convenience method)
  const leaveProjectRoom = (projectId: number) => {
    return leaveRoom(`project_${projectId}`)
  }

  return {
    // State
    isConnected,
    isConnecting,
    connectionError,
    connectionState,
    notifications,
    userRooms,

    // Connection methods
    connect,
    disconnect,

    // Room methods
    joinRoom,
    leaveRoom,
    joinProjectRoom,
    leaveProjectRoom,

    // Message methods
    sendMessage,
    sendText,
    sendRoomMessage,
    broadcast,

    // Notification methods
    addNotification,
    removeNotification,
    clearNotifications,

    // Handler registration
    onMessage,
  }
})
