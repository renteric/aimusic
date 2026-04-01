/**
 * auth.ts - Pinia authentication store for AI-Powered-Music.
 *
 * Manages the logged-in user state including role. Views and the router
 * navigation guard read `isAuthenticated` and role helpers to decide whether
 * to show protected content or redirect to the login page.
 */

import { authApi } from '@/services/api'
import type { UserRole } from '@/services/types'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  /** Username of the authenticated user, or null when not logged in. */
  const username = ref<string | null>(null)

  /** Role of the authenticated user, or null when not logged in. */
  const role = ref<UserRole | null>(null)

  /** True after the initial /api/auth/me check completes. */
  const initialized = ref(false)

  /** True when a login or logout request is in flight. */
  const loading = ref(false)

  /** True when the user has an active session. */
  const isAuthenticated = computed(() => username.value !== null)

  /** True when the user can access the admin panel (superadmin or admin). */
  const isAdmin = computed(() => role.value === 'superadmin' || role.value === 'admin')

  /** True when the user has the viewer role (restricted actions). */
  const isViewer = computed(() => role.value === 'viewer')

  /**
   * Check the current session by calling /api/auth/me.
   * Sets `initialized` to true regardless of the result.
   */
  async function fetchMe(): Promise<void> {
    try {
      const { data } = await authApi.me()
      if (data.authenticated && data.username) {
        username.value = data.username
        role.value = data.role ?? null
      } else {
        username.value = null
        role.value = null
      }
    } catch {
      username.value = null
      role.value = null
    } finally {
      initialized.value = true
    }
  }

  /**
   * Authenticate with username and password.
   *
   * @param user - Login name.
   * @param password - Plain-text password.
   * @throws Error with a user-facing message on failure.
   */
  async function login(user: string, password: string): Promise<void> {
    loading.value = true
    try {
      const { data } = await authApi.login(user, password)
      if (!data.success) throw new Error(data.error ?? 'Login failed.')
      username.value = data.username ?? user
      role.value = data.role ?? null
    } finally {
      loading.value = false
    }
  }

  /** End the current session and clear local state. */
  async function logout(): Promise<void> {
    loading.value = true
    try {
      await authApi.logout()
    } finally {
      username.value = null
      role.value = null
      loading.value = false
    }
  }

  return { username, role, initialized, loading, isAuthenticated, isAdmin, isViewer, fetchMe, login, logout }
})
