<script setup lang="ts">
/**
 * App.vue - Root component for AI-Powered-Music.
 *
 * Renders NavBar for authenticated users and the router-view outlet.
 * The navigation guard in router/index.ts handles redirecting unauthenticated
 * requests to /login before this component even mounts.
 */

import NavBar from '@/components/NavBar.vue'
import { useAuthStore } from '@/stores/auth'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

const auth = useAuthStore()
const route = useRoute()
const { t } = useI18n()

/** Show the navbar everywhere except the login page. */
const showNav = computed(() => route.name !== 'Login')
</script>

<template>
  <div class="d-flex flex-column min-vh-100">
    <NavBar v-if="showNav && auth.isAuthenticated" />
    <main class="flex-grow-1">
      <RouterView />
    </main>
    <footer v-if="showNav && auth.isAuthenticated" class="app-footer py-3 text-center text-muted small">
      &copy; 2026 {{ t('common.app_name') }}
    </footer>
  </div>
</template>
