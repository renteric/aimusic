<script setup lang="ts">
/**
 * AdminView.vue - User management page for superadmin and admin roles.
 *
 * Lists all users with create, edit, and delete actions.
 * The superadmin account cannot be deleted and its role cannot be changed.
 */

import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi } from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { ASSIGNABLE_ROLES } from '@/services/types'
import type { UserRecord, UserRole } from '@/services/types'

const auth = useAuthStore()
const { t } = useI18n()

// ── State ─────────────────────────────────────────────────────────────────────

const users = ref<UserRecord[]>([])

// ── Sorting ───────────────────────────────────────────────────────────────────

type SortKey = 'id' | 'username' | 'role' | 'is_active' | 'created_at'
const sortKey = ref<SortKey>('id')
const sortAsc = ref(true)

function applySort(key: SortKey): void {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = true
  }
}

const sortedUsers = computed(() => {
  const copy = [...users.value]
  const key = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  return copy.sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
    if (typeof av === 'boolean' && typeof bv === 'boolean') return (Number(bv) - Number(av)) * dir
    return String(av).localeCompare(String(bv)) * dir
  })
})
const loading = ref(false)
const pageError = ref('')

// ── Modal ─────────────────────────────────────────────────────────────────────

const showModal = ref(false)
/** null = create mode, UserRecord = edit mode */
const editingUser = ref<UserRecord | null>(null)

const form = reactive({
  username: '',
  password: '',
  role: 'user' as UserRole,
  is_active: true,
})

const formError = ref('')
const saving = ref(false)

// ── Delete ─────────────────────────────────────────────────────────────────────

const deletingId = ref<number | null>(null)

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(loadUsers)

// ── Helpers ───────────────────────────────────────────────────────────────────

function roleBadgeClass(role: string): string {
  const map: Record<string, string> = {
    superadmin: 'bg-danger',
    admin: 'bg-warning text-dark',
    user: 'bg-primary',
    viewer: 'bg-secondary',
  }
  return map[role] ?? 'bg-secondary'
}

function isUndeletable(user: UserRecord): boolean {
  return user.role === 'superadmin'
}

function isSelf(user: UserRecord): boolean {
  return user.username === auth.username
}

// ── Data ──────────────────────────────────────────────────────────────────────

async function loadUsers(): Promise<void> {
  loading.value = true
  pageError.value = ''
  try {
    const { data } = await adminApi.listUsers()
    users.value = data.users
  } catch {
    pageError.value = t('admin.error_load')
  } finally {
    loading.value = false
  }
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function openCreate(): void {
  editingUser.value = null
  form.username = ''
  form.password = ''
  form.role = 'user'
  form.is_active = true
  formError.value = ''
  showModal.value = true
}

function openEdit(user: UserRecord): void {
  if (user.role === 'superadmin' && auth.role !== 'superadmin') return
  editingUser.value = user
  form.username = user.username
  form.password = ''
  form.role = user.role === 'superadmin' ? 'superadmin' : user.role
  form.is_active = user.is_active
  formError.value = ''
  showModal.value = true
}

function closeModal(): void {
  showModal.value = false
}

async function handleSave(): Promise<void> {
  formError.value = ''
  saving.value = true
  try {
    if (editingUser.value === null) {
      if (!form.username.trim() || !form.password) {
        formError.value = t('admin.error_required')
        return
      }
      const { data } = await adminApi.createUser(form.username.trim(), form.password, form.role)
      if (!data.success) {
        formError.value = data.error ?? t('admin.error_create_failed')
        return
      }
    } else {
      if (editingUser.value.role === 'superadmin' && auth.role !== 'superadmin') {
        formError.value = t('admin.error_superadmin_only')
        return
      }
      const fields: { username?: string; password?: string; role?: UserRole; is_active?: boolean } = {}
      if (form.username.trim() && form.username.trim() !== editingUser.value.username) {
        fields.username = form.username.trim()
      }
      if (form.password) {
        fields.password = form.password
      }
      if (editingUser.value.role !== 'superadmin' && form.role !== editingUser.value.role) {
        fields.role = form.role
      }
      if (form.is_active !== editingUser.value.is_active) {
        fields.is_active = form.is_active
      }
      const { data } = await adminApi.updateUser(editingUser.value.id, fields)
      if (!data.success) {
        formError.value = data.error ?? t('admin.error_update_failed')
        return
      }
    }
    showModal.value = false
    await loadUsers()
  } catch {
    formError.value = t('common.request_failed')
  } finally {
    saving.value = false
  }
}

// ── Delete ─────────────────────────────────────────────────────────────────────

async function handleDelete(user: UserRecord): Promise<void> {
  if (!confirm(t('admin.confirm_delete', { username: user.username }))) return
  deletingId.value = user.id
  try {
    const { data } = await adminApi.deleteUser(user.id)
    if (!data.success) {
      alert(data.error ?? t('admin.error_delete_failed'))
      return
    }
    await loadUsers()
  } catch {
    alert(t('common.request_failed'))
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="container py-5">
    <div class="row justify-content-center">
      <div class="col-lg-10">

        <!-- Header -->
        <div class="d-flex align-items-center justify-content-between mb-4">
          <h2 class="mb-0 fw-bold">
            <i class="bi bi-people me-2 text-primary"></i>{{ t('admin.title') }}
          </h2>
          <button class="btn btn-primary" @click="openCreate">
            <i class="bi bi-person-plus me-1"></i>{{ t('admin.new_user') }}
          </button>
        </div>

        <!-- Page error -->
        <div v-if="pageError" class="alert alert-danger">{{ pageError }}</div>

        <!-- Users table -->
        <div class="card border-0 shadow-sm">
          <div class="card-body p-0">
            <div class="table-responsive">
              <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                  <tr>
                    <th class="sortable-col" @click="applySort('id')">
                      {{ t('admin.col_id') }}
                      <i class="bi ms-1" :class="sortKey === 'id' ? (sortAsc ? 'bi-sort-up' : 'bi-sort-down') : 'bi-arrow-down-up text-up-down-muted'"></i>
                    </th>
                    <th class="sortable-col" @click="applySort('username')">
                      {{ t('admin.col_username') }}
                      <i class="bi ms-1" :class="sortKey === 'username' ? (sortAsc ? 'bi-sort-alpha-up' : 'bi-sort-alpha-down') : 'bi-arrow-down-up text-up-down-muted'"></i>
                    </th>
                    <th class="sortable-col" @click="applySort('role')">
                      {{ t('admin.col_role') }}
                      <i class="bi ms-1" :class="sortKey === 'role' ? (sortAsc ? 'bi-sort-alpha-up' : 'bi-sort-alpha-down') : 'bi-arrow-down-up text-up-down-muted'"></i>
                    </th>
                    <th class="sortable-col" @click="applySort('is_active')">
                      {{ t('admin.col_status') }}
                      <i class="bi ms-1" :class="sortKey === 'is_active' ? (sortAsc ? 'bi-sort-up' : 'bi-sort-down') : 'bi-arrow-down-up text-up-down-muted'"></i>
                    </th>
                    <th class="sortable-col" @click="applySort('created_at')">
                      {{ t('admin.col_created') }}
                      <i class="bi ms-1" :class="sortKey === 'created_at' ? (sortAsc ? 'bi-sort-up' : 'bi-sort-down') : 'bi-arrow-down-up text-up-down-muted'"></i>
                    </th>
                    <th>{{ t('common.actions') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <!-- Loading -->
                  <tr v-if="loading">
                    <td colspan="6" class="text-center py-4">
                      <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
                    </td>
                  </tr>

                  <!-- Rows -->
                  <tr v-for="user in sortedUsers" :key="user.id">
                    <td class="text-muted">{{ user.id }}</td>
                    <td>
                      <span class="fw-semibold">{{ user.username }}</span>
                      <span v-if="isSelf(user)" class="badge bg-info ms-2 small">{{ t('admin.badge_you') }}</span>
                    </td>
                    <td>
                      <span class="badge" :class="roleBadgeClass(user.role)">{{ user.role }}</span>
                    </td>
                    <td>
                      <span v-if="user.is_active" class="badge bg-success">{{ t('admin.status_active') }}</span>
                      <span v-else class="badge bg-secondary">{{ t('admin.status_disabled') }}</span>
                    </td>
                    <td class="text-muted text-nowrap small">{{ user.created_at }}</td>
                    <td>
                      <div class="d-flex gap-2">
                        <button
                          class="btn btn-sm btn-outline-secondary"
                          :disabled="user.role === 'superadmin' && auth.role !== 'superadmin'"
                          :title="user.role === 'superadmin' && auth.role !== 'superadmin' ? t('admin.only_superadmin_edit') : t('common.edit')"
                          @click="openEdit(user)"
                        >
                          <i class="bi bi-pencil"></i>
                        </button>
                        <button
                          class="btn btn-sm btn-outline-danger"
                          :disabled="isUndeletable(user) || isSelf(user) || deletingId === user.id"
                          :title="isUndeletable(user) ? t('admin.cannot_delete_superadmin') : isSelf(user) ? t('admin.cannot_delete_self') : t('common.delete')"
                          @click="handleDelete(user)"
                        >
                          <span v-if="deletingId === user.id" class="spinner-border spinner-border-sm"></span>
                          <i v-else class="bi bi-trash"></i>
                        </button>
                      </div>
                    </td>
                  </tr>

                  <!-- Empty -->
                  <tr v-if="!loading && users.length === 0">
                    <td colspan="6" class="text-center py-4 text-muted">{{ t('admin.no_users') }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>

  <!-- Create / Edit modal -->
  <div
    v-if="showModal"
    class="modal d-block modal-overlay"
    tabindex="-1"
    @click.self="closeModal"
  >
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content border-0 shadow">
        <div class="modal-header">
          <h5 class="modal-title fw-bold">
            <i class="bi" :class="editingUser ? 'bi-pencil' : 'bi-person-plus'"></i>
            {{ editingUser ? t('admin.modal_edit_title', { username: editingUser.username }) : t('admin.modal_create_title') }}
          </h5>
          <button type="button" class="btn-close" @click="closeModal"></button>
        </div>
        <div class="modal-body">

          <div v-if="formError" class="alert alert-danger py-2 small">{{ formError }}</div>

          <div class="mb-3">
            <label class="form-label fw-semibold">{{ t('admin.form_username') }}</label>
            <input v-model="form.username" type="text" class="form-control" placeholder="username" />
          </div>

          <div class="mb-3">
            <label class="form-label fw-semibold">
              {{ t('admin.form_password') }}
              <span v-if="editingUser" class="text-muted fw-normal">({{ t('admin.form_password_hint') }})</span>
            </label>
            <input v-model="form.password" type="password" class="form-control" placeholder="••••••••" />
          </div>

          <div class="mb-3">
            <label class="form-label fw-semibold">{{ t('admin.form_role') }}</label>
            <select
              v-model="form.role"
              class="form-select"
              :disabled="editingUser?.role === 'superadmin'"
            >
              <option v-if="editingUser?.role === 'superadmin'" value="superadmin">superadmin</option>
              <option v-for="r in ASSIGNABLE_ROLES" :key="r" :value="r">{{ r }}</option>
            </select>
            <div v-if="editingUser?.role === 'superadmin'" class="form-text text-muted">
              {{ t('admin.superadmin_role_locked') }}
            </div>
          </div>

          <div class="form-check">
            <input
              id="modal-is-active"
              v-model="form.is_active"
              type="checkbox"
              class="form-check-input"
            />
            <label for="modal-is-active" class="form-check-label">{{ t('admin.form_active') }}</label>
          </div>

        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeModal">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" :disabled="saving" @click="handleSave">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
            {{ editingUser ? t('admin.save_changes') : t('admin.create_user') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
