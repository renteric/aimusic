<script setup lang="ts">
/**
 * ProfileView.vue - Logged-in user profile page for AI-Music.
 *
 * Shows the current user's account information and allows changing
 * their own password.
 */

import { authApi } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const auth = useAuthStore()
const { t } = useI18n()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')

const saving = ref(false)
const successMsg = ref('')
const errorMsg = ref('')

async function changePassword(): Promise<void> {
  successMsg.value = ''
  errorMsg.value = ''

  if (!currentPassword.value || !newPassword.value) {
    errorMsg.value = t('profile.error_fields')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    errorMsg.value = t('profile.error_mismatch')
    return
  }
  if (newPassword.value.length < 6) {
    errorMsg.value = t('profile.error_too_short')
    return
  }

  saving.value = true
  try {
    const { data } = await authApi.changePassword(currentPassword.value, newPassword.value)
    if (!data.success) throw new Error(data.error ?? t('profile.error_failed'))
    successMsg.value = t('profile.success')
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (err: any) {
    errorMsg.value = err.response?.data?.detail ?? err.message ?? t('profile.error_failed')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="container py-4 profile-container">
    <h2 class="mb-4 fw-bold">
      <i class="bi bi-person me-2"></i>{{ t('profile.title') }}
    </h2>

    <!-- Account info card -->
    <div class="card mb-4">
      <div class="card-body">
        <h5 class="card-title mb-3">{{ t('profile.account_info') }}</h5>
        <dl class="row mb-0">
          <dt class="col-4 text-muted fw-normal">{{ t('profile.username') }}</dt>
          <dd class="col-8 fw-semibold mb-2">{{ auth.username }}</dd>
          <dt class="col-4 text-muted fw-normal">{{ t('profile.role') }}</dt>
          <dd class="col-8 mb-0">
            <span class="badge bg-primary text-capitalize">{{ auth.role }}</span>
          </dd>
        </dl>
      </div>
    </div>

    <!-- Change password card (not available for viewers) -->
    <div v-if="auth.isViewer" class="alert alert-secondary py-2 small mb-4">
      <i class="bi bi-lock me-1"></i>{{ t('profile.viewer_locked') }}
    </div>

    <div v-else class="card">
      <div class="card-body">
        <h5 class="card-title mb-3">{{ t('profile.change_password') }}</h5>

        <div v-if="successMsg" class="alert alert-success py-2 small">
          <i class="bi bi-check-circle me-1"></i>{{ successMsg }}
        </div>
        <div v-if="errorMsg" class="alert alert-danger py-2 small">
          <i class="bi bi-exclamation-triangle me-1"></i>{{ errorMsg }}
        </div>

        <form @submit.prevent="changePassword">
          <div class="mb-3">
            <label class="form-label">{{ t('profile.current_password') }}</label>
            <input
              v-model="currentPassword"
              type="password"
              class="form-control"
              autocomplete="current-password"
              :disabled="saving"
            />
          </div>
          <div class="mb-3">
            <label class="form-label">{{ t('profile.new_password') }}</label>
            <input
              v-model="newPassword"
              type="password"
              class="form-control"
              autocomplete="new-password"
              :disabled="saving"
            />
          </div>
          <div class="mb-4">
            <label class="form-label">{{ t('profile.confirm_password') }}</label>
            <input
              v-model="confirmPassword"
              type="password"
              class="form-control"
              autocomplete="new-password"
              :disabled="saving"
            />
          </div>
          <button type="submit" class="btn btn-primary" :disabled="saving">
            <span v-if="saving" class="spinner-border spinner-border-sm me-2"></span>
            {{ saving ? t('profile.saving_btn') : t('profile.save_btn') }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
