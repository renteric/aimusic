<script setup lang="ts">
/**
 * MediaFilesView.vue - Media file browser with sort, play, delete, and metadata tools.
 *
 * Fetches directory listings from /api/media/files/:path.
 * The current path is derived from the router params so deep-links work.
 * Audio playback is handled by the shared usePlayer composable.
 */

import { usePlayer } from '@/composables/usePlayer'
import { mediaApi } from '@/services/api'
import type { MediaEntry } from '@/services/types'
import { useAuthStore } from '@/stores/auth'
import { marked } from 'marked'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

const auth = useAuthStore()
const { t } = useI18n()

// ── Router + player ───────────────────────────────────────────────────────────

const route = useRoute()
const router = useRouter()
const { play, activeUrl, isPlaying, progress } = usePlayer()

// ── State ─────────────────────────────────────────────────────────────────────

const entries = ref<MediaEntry[]>([])
const currentPath = ref('media')
const parentPath = ref<string | null>(null)
const reqPath = ref('')
const loading = ref(false)
const error = ref('')

// Sorting
const sortCol = ref<keyof MediaEntry>('name')
const sortAsc = ref(true)

// Selection
const selectedPaths = ref<Set<string>>(new Set())

// Metadata cleaner
const cleanOptions = ref({ show: false, clean: false, backup: false, recursive: true, remove_protection: false })
const cleanOutput = ref('')
const cleanRunning = ref(false)
const cleanError = ref('')

// Transcribe
const transcribeRunning = ref<string | null>(null)

// Markdown viewer
const mdTitle = ref('')
const mdContent = ref('')
const mdLoading = ref(false)
const showMdModal = ref(false)

// Delete
const deleteRunning = ref(false)

// ── Computed ──────────────────────────────────────────────────────────────────

const sortedEntries = computed(() => {
  const col = sortCol.value
  return [...entries.value].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
    let av: string | number = a[col] as string | number
    let bv: string | number = b[col] as string | number
    if (col === 'name') {
      av = (av as string).toLowerCase()
      bv = (bv as string).toLowerCase()
    }
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortAsc.value ? cmp : -cmp
  })
})

const selectedCount = computed(() => selectedPaths.value.size)
const allSelected = computed(
  () => entries.value.length > 0 && selectedCount.value === entries.value.length,
)

// ── Clean option labels ───────────────────────────────────────────────────────

const cleanOptionLabels: Record<string, string> = {
  show: 'media.clean_show',
  clean: 'media.clean_clean',
  backup: 'media.clean_backup',
  recursive: 'media.clean_recursive',
  remove_protection: 'media.clean_remove_protection',
}

// ── Path helpers ──────────────────────────────────────────────────────────────

function currentReqPath(): string {
  const param = route.params.pathMatch
  if (!param) return ''
  return Array.isArray(param) ? param.join('/') : param
}

function navigateTo(path: string): void {
  if (path === '') {
    router.push({ name: 'MediaFiles' })
  } else {
    router.push({ name: 'MediaFilesNested', params: { pathMatch: path.split('/') } })
  }
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadDirectory(path: string): Promise<void> {
  loading.value = true
  error.value = ''
  selectedPaths.value = new Set()
  cleanOutput.value = ''
  try {
    const { data } = await mediaApi.listFiles(path)
    entries.value = data.entries
    currentPath.value = data.current_path
    parentPath.value = data.parent_path
    reqPath.value = data.req_path
  } catch {
    error.value = t('media.error_load')
  } finally {
    loading.value = false
  }
}

onMounted(() => loadDirectory(currentReqPath()))
watch(() => route.params.pathMatch, () => loadDirectory(currentReqPath()))

// ── Sorting ───────────────────────────────────────────────────────────────────

function applySort(col: keyof MediaEntry): void {
  if (sortCol.value === col) {
    sortAsc.value = !sortAsc.value
  } else {
    sortCol.value = col
    sortAsc.value = true
  }
}

function sortIcon(col: keyof MediaEntry): string {
  if (sortCol.value !== col) return 'bi-arrow-down-up text-up-down-muted opacity-50'
  return sortAsc.value ? 'bi-arrow-up arrow-up-down' : 'bi-arrow-down arrow-up-down'
}

// ── Selection ─────────────────────────────────────────────────────────────────

function toggleAll(checked: boolean): void {
  selectedPaths.value = checked ? new Set(entries.value.map((e) => e.rel_path)) : new Set()
  cleanError.value = ''
}

function toggleEntry(relPath: string, checked: boolean): void {
  const s = new Set(selectedPaths.value)
  checked ? s.add(relPath) : s.delete(relPath)
  selectedPaths.value = s
  cleanError.value = ''
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function handleDelete(): Promise<void> {
  const paths = [...selectedPaths.value]
  if (!paths.length) return

  const names = paths.join('\n')
  if (!confirm(`${t('media.confirm_delete', { n: paths.length })}\n\n${names}`)) return

  deleteRunning.value = true
  try {
    const { data } = await mediaApi.deleteFiles(paths)
    if (data.errors.length) alert(t('media.delete_errors') + '\n' + data.errors.join('\n'))
    await loadDirectory(currentReqPath())
  } catch {
    alert(t('media.delete_failed'))
  } finally {
    deleteRunning.value = false
  }
}

// ── Metadata cleaner ──────────────────────────────────────────────────────────

async function handleClean(): Promise<void> {
  if (selectedPaths.value.size === 0) {
    cleanError.value = t('media.error_select_clean')
    return
  }
  cleanError.value = ''
  cleanRunning.value = true
  cleanOutput.value = ''
  const paths = [...selectedPaths.value]
  try {
    for (const p of paths) {
      const { data } = await mediaApi.cleanMetadata({ path: p, ...cleanOptions.value })
      if (paths.length > 1) cleanOutput.value += `\n── ${p} ──\n`
      cleanOutput.value += data.output ?? data.error ?? '(no output)'
    }
  } catch {
    cleanOutput.value = t('common.request_failed')
  } finally {
    cleanRunning.value = false
  }
}

// ── Transcribe ────────────────────────────────────────────────────────────────

async function handleTranscribe(entry: MediaEntry): Promise<void> {
  transcribeRunning.value = entry.rel_path
  try {
    const { data } = await mediaApi.transcribe(entry.rel_path)
    if (data.success) {
      alert(t('media.transcription_complete') + '\n\n' + (data.output ?? '').slice(0, 500))
    } else {
      alert(t('media.transcription_failed') + '\n\n' + (data.error ?? 'Unknown error'))
    }
  } catch {
    alert(t('media.transcription_request_failed'))
  } finally {
    transcribeRunning.value = null
  }
}

// ── Markdown viewer ───────────────────────────────────────────────────────────

async function openMarkdown(entry: MediaEntry): Promise<void> {
  mdTitle.value = entry.name
  mdContent.value = ''
  mdLoading.value = true
  showMdModal.value = true
  try {
    const { data } = await mediaApi.readFile(entry.rel_path)
    mdContent.value = marked.parse(data.content) as string
  } catch {
    mdContent.value = `<p class="text-danger">${t('common.request_failed')}</p>`
  } finally {
    mdLoading.value = false
  }
}

// ── Player helpers ────────────────────────────────────────────────────────────

function playEntry(entry: MediaEntry): void {
  play(mediaApi.streamUrl(entry.rel_path))
}

function isActive(entry: MediaEntry): boolean {
  return activeUrl.value === mediaApi.streamUrl(entry.rel_path)
}
</script>

<template>
  <div class="container py-4">

    <!-- Header -->
    <div class="mb-3">
      <h2 class="mb-0 fw-bold">
        <i class="bi bi-folder2-open me-2 text-primary"></i>{{ t('media.title') }}
      </h2>
      <code class="text-muted small">/{{ currentPath }}</code>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <!-- Metadata Cleaner panel (hidden for viewer role) -->
    <div v-if="!auth.isViewer" class="card border-0 shadow-sm mb-2">
      <div class="card-header d-flex align-items-center justify-content-between py-2">
        <strong class="small">
          <i class="bi bi-tags me-1"></i>{{ t('media.metadata_cleaner') }}
        </strong>
        <span class="text-muted small">
          {{ selectedCount > 0 ? t('media.n_selected', { n: selectedCount }) : t('media.no_selection') }}
        </span>
      </div>
      <div class="card-body py-3">
        <div class="d-flex flex-wrap gap-3 align-items-center">
          <div v-for="(_, key) in cleanOptions" :key="key" class="form-check mb-0">
            <input
              :id="`chk-${key}`"
              v-model="(cleanOptions as any)[key]"
              type="checkbox"
              class="form-check-input"
            />
            <label :for="`chk-${key}`" class="form-check-label small">
              {{ t(cleanOptionLabels[key as string] ?? key as string) }}
            </label>
          </div>
          <button
            class="btn btn-sm btn-outline-primary ms-auto"
            :disabled="cleanRunning"
            @click="handleClean"
          >
            <span v-if="cleanRunning" class="spinner-border spinner-border-sm me-1"></span>
            {{ cleanRunning ? t('common.running') : t('common.run') }}
          </button>
        </div>
        <div v-if="cleanError" class="text-danger small mt-2">
          <i class="bi bi-exclamation-circle me-1"></i>{{ cleanError }}
        </div>
        <pre v-if="cleanOutput" class="log-terminal mt-3 p-3 small">{{ cleanOutput }}</pre>
      </div>
    </div>

    <!-- Up button -->
    <div class="mb-3">
      <button
        v-if="parentPath !== null"
        class="btn btn-outline-secondary btn-sm"
        @click="navigateTo(parentPath ?? '')"
      >
        <i class="bi bi-arrow-up me-1"></i>{{ t('common.up') }}
      </button>
    </div>

    <!-- File table -->
    <div class="card border-0 shadow-sm">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th v-if="!auth.isViewer" class="col-checkbox">
                  <input
                    type="checkbox"
                    class="form-check-input"
                    :checked="allSelected"
                    :indeterminate="selectedCount > 0 && !allSelected"
                    @change="toggleAll(($event.target as HTMLInputElement).checked)"
                  />
                </th>
                <th class="sortable-col" @click="applySort('name')">
                  {{ t('common.name') }} <i :class="['bi', sortIcon('name')]"></i>
                </th>
                <th class="sortable-col text-end" @click="applySort('size')">
                  {{ t('media.size') }} <i :class="['bi', sortIcon('size')]"></i>
                </th>
                <th class="sortable-col" @click="applySort('mime')">
                  {{ t('media.type') }} <i :class="['bi', sortIcon('mime')]"></i>
                </th>
                <th class="sortable-col" @click="applySort('mtime')">
                  {{ t('common.modified') }} <i :class="['bi', sortIcon('mtime')]"></i>
                </th>
                <th>{{ t('common.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <!-- Loading skeleton -->
              <tr v-if="loading">
                <td :colspan="auth.isViewer ? 5 : 6" class="text-center py-4">
                  <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
                </td>
              </tr>

              <!-- Entries -->
              <tr
                v-for="entry in sortedEntries"
                :key="entry.rel_path"
                :class="{ 'table-active': selectedPaths.has(entry.rel_path) }"
              >
                <!-- Checkbox (hidden for viewer) -->
                <td v-if="!auth.isViewer">
                  <input
                    type="checkbox"
                    class="form-check-input"
                    :checked="selectedPaths.has(entry.rel_path)"
                    @change="toggleEntry(entry.rel_path, ($event.target as HTMLInputElement).checked)"
                  />
                </td>

                <!-- Name -->
                <td>
                  <button
                    v-if="entry.is_dir"
                    class="btn btn-link p-0 text-decoration-none"
                    @click="navigateTo(entry.rel_path)"
                  >
                    <i class="bi bi-folder-fill text-warning me-1"></i>{{ entry.name }}/
                  </button>
                  <span v-else>
                    <i v-if="entry.mime.startsWith('audio/')" class="bi bi-file-earmark-music text-primary me-1"></i>
                    <i v-else-if="entry.name.endsWith('.md')" class="bi bi-file-earmark-text text-success me-1"></i>
                    <i v-else class="bi bi-file-earmark text-muted me-1"></i>
                    <button
                      v-if="entry.name.endsWith('.md')"
                      class="btn btn-link p-0 text-decoration-none text-success"
                      @click="openMarkdown(entry)"
                    >{{ entry.name }}</button>
                    <span v-else>{{ entry.name }}</span>
                  </span>
                </td>

                <!-- Size -->
                <td class="text-end text-nowrap">
                  <span v-if="entry.is_dir" class="text-muted">—</span>
                  <span v-else>{{ entry.size_human }}</span>
                </td>

                <!-- Type -->
                <td class="text-nowrap">
                  <code class="text-muted small">{{ entry.is_dir ? t('media.directory') : entry.mime }}</code>
                </td>

                <!-- Modified -->
                <td class="text-muted text-nowrap">{{ entry.mtime }}</td>

                <!-- Actions -->
                <td>
                  <div v-if="!entry.is_dir" class="d-flex align-items-center gap-1 flex-wrap">
                    <!-- Download -->
                    <a
                      :href="mediaApi.downloadUrl(entry.rel_path)"
                      class="btn btn-sm btn-outline-secondary"
                      :title="t('common.actions')"
                    >
                      <i class="bi bi-download"></i>
                    </a>

                    <!-- Play / pause (audio only) -->
                    <div v-if="entry.mime.startsWith('audio/')" class="d-flex align-items-center gap-2">
                      <button
                        class="btn btn-sm"
                        :class="isActive(entry) && isPlaying ? 'btn-success' : 'btn-outline-success'"
                        @click="playEntry(entry)"
                        title="Play / Pause"
                      >
                        <i :class="['bi', isActive(entry) && isPlaying ? 'bi-pause-fill' : 'bi-play-fill']"></i>
                      </button>
                      <div v-if="isActive(entry)" class="progress media-progress">
                        <div class="progress-bar" :style="{ width: progress + '%' }"></div>
                      </div>
                    </div>

                    <!-- View transcript (.md files) -->
                    <button
                      v-if="entry.name.endsWith('.md')"
                      class="btn btn-sm btn-outline-success"
                      @click="openMarkdown(entry)"
                      title="View"
                    >
                      <i class="bi bi-eye"></i>
                    </button>

                    <!-- Transcribe (audio only, hidden for viewer) -->
                    <button
                      v-if="entry.mime.startsWith('audio/') && !auth.isViewer"
                      class="btn btn-sm btn-outline-info"
                      :disabled="transcribeRunning === entry.rel_path"
                      @click="handleTranscribe(entry)"
                      title="Transcribe"
                    >
                      <span v-if="transcribeRunning === entry.rel_path" class="spinner-border spinner-border-sm"></span>
                      <i v-else class="bi bi-mic"></i>
                    </button>
                  </div>
                  <span v-else class="text-muted">—</span>
                </td>
              </tr>

              <!-- Empty state -->
              <tr v-if="!loading && entries.length === 0">
                <td :colspan="auth.isViewer ? 5 : 6" class="text-center py-5 text-muted">
                  <i class="bi bi-folder2 display-6 d-block mb-2"></i>
                  {{ t('media.no_files') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Footer: delete selected (hidden for viewer) -->
      <div v-if="!auth.isViewer" class="card-footer d-flex justify-content-end py-2">
        <button
          class="btn btn-sm btn-danger"
          :disabled="selectedCount === 0 || deleteRunning"
          @click="handleDelete"
        >
          <span v-if="deleteRunning" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-trash me-1"></i>
          {{ selectedCount > 0 ? t('media.delete_n', { n: selectedCount }) : t('media.delete_selected') }}
        </button>
      </div>
    </div>

  </div>

  <!-- Markdown viewer modal -->
  <div
    v-if="showMdModal"
    class="modal-overlay md-viewer-overlay position-fixed top-0 start-0 w-100 h-100 d-flex align-items-start justify-content-center pt-5"
    @click.self="showMdModal = false"
  >
    <div class="card border-0 shadow-lg md-viewer-card">
      <div class="card-header d-flex align-items-center justify-content-between py-2">
        <strong class="small text-truncate me-3">
          <i class="bi bi-file-earmark-text text-success me-1"></i>{{ mdTitle }}
        </strong>
        <button class="btn btn-sm btn-outline-secondary" @click="showMdModal = false">
          {{ t('common.close') }}
        </button>
      </div>
      <div class="card-body overflow-auto md-viewer-body">
        <div v-if="mdLoading" class="text-center py-5">
          <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
        </div>
        <div v-else class="doc-preview" v-html="mdContent"></div>
      </div>
    </div>
  </div>

</template>
