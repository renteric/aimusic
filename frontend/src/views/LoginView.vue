<script setup lang="ts">
/**
 * LoginView.vue - Login page for AI-Powered-Music.
 *
 * Submits credentials to the auth store, which calls POST /api/auth/login.
 * On success, the user is navigated to the home page. Errors are displayed
 * inline below the form.
 */

import { setLocale, type Locale } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()
const { t, locale } = useI18n()

const username = ref('')
const password = ref('')
const errorMsg = ref('')

interface LanguageOption {
  code: Locale
  label: string
  flag: string
}

const languages: LanguageOption[] = [
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
  { code: 'es', label: 'Español', flag: '🇪🇸' },
]

/**
 * Handle form submission.
 * Delegates to the auth store and redirects on success.
 */
async function handleSubmit(): Promise<void> {
  errorMsg.value = ''
  if (!username.value.trim() || !password.value) {
    errorMsg.value = t('login.error_empty')
    return
  }
  try {
    await auth.login(username.value.trim(), password.value)
    router.push({ name: 'Home' })
  } catch (err: unknown) {
    errorMsg.value = err instanceof Error ? err.message : t('login.error_failed')
  }
}
</script>

<template>
  <div class="login-page d-flex align-items-center justify-content-center min-vh-100 bg-dark">
    <div class="login-card card border-0 shadow-lg">
      <div class="card-body p-5">
        <!-- Logo / heading -->
        <div class="text-center mb-4">
          <i class="bi bi-music-note-beamed display-4 text-primary"></i>
          <h1 class="h4 fw-bold mt-2 mb-0">{{ t('common.app_name') }}</h1>
          <p class="text-muted small mt-1">{{ t('login.subtitle') }}</p>
        </div>

        <!-- Error alert -->
        <div v-if="errorMsg" class="alert alert-danger alert-sm py-2" role="alert">
          <i class="bi bi-exclamation-triangle-fill me-2"></i>{{ errorMsg }}
        </div>

        <!-- Login form -->
        <form @submit.prevent="handleSubmit" novalidate>
          <div class="mb-3">
            <label for="username" class="form-label fw-semibold">{{ t('login.username') }}</label>
            <div class="input-group">
              <span class="input-group-text"><i class="bi bi-person"></i></span>
              <input
                id="username"
                v-model="username"
                type="text"
                class="form-control"
                :placeholder="t('login.username_placeholder')"
                autocomplete="username"
                required
                :disabled="auth.loading"
              />
            </div>
          </div>

          <div class="mb-4">
            <label for="password" class="form-label fw-semibold">{{ t('login.password') }}</label>
            <div class="input-group">
              <span class="input-group-text"><i class="bi bi-lock"></i></span>
              <input
                id="password"
                v-model="password"
                type="password"
                class="form-control"
                :placeholder="t('login.password_placeholder')"
                autocomplete="current-password"
                required
                :disabled="auth.loading"
              />
            </div>
          </div>

          <button
            type="submit"
            class="btn btn-primary w-100 py-2 fw-semibold"
            :disabled="auth.loading"
          >
            <span v-if="auth.loading" class="spinner-border spinner-border-sm me-2" role="status"></span>
            {{ auth.loading ? t('login.submitting') : t('login.submit') }}
          </button>
        </form>

        <!-- Language switcher -->
        <div class="d-flex justify-content-center gap-2 mt-4">
          <button
            v-for="lang in languages"
            :key="lang.code"
            class="btn btn-sm"
            :class="locale === lang.code ? 'btn-primary' : 'btn-outline-secondary'"
            @click="setLocale(lang.code)"
            :title="lang.label"
          >
            {{ lang.flag }} {{ lang.label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
