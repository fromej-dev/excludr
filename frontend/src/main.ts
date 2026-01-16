import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './assets/index.css'

const app = createApp(App)

// Enable Vue DevTools in development
if (import.meta.env.DEV) {
  app.config.performance = true
}

app.use(createPinia())
app.use(router)

app.mount('#app')
