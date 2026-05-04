/**
 * main.ts - Application entry point for AI-Music.
 *
 * Initialises Vue 3 with Pinia (state management) and Vue Router,
 * loads Bootstrap CSS, and mounts the root App component.
 */

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import router from './router'

// Bootstrap CSS + JS — bundled by Vite, no CDN required.
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'

// Project-level styles (overrides and custom utilities).
import './assets/css/main.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(i18n)

app.mount('#app')
