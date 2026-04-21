<script setup lang="ts">
/**
 * MediaFilesView.vue - Media file browser with sort, play, delete, metadata tools, and AI panel.
 *
 * Fetches directory listings from /api/media/files/:path.
 * The current path is derived from the router params so deep-links work.
 * Audio playback is handled by the shared usePlayer composable.
 */

import { usePlayer } from '@/composables/usePlayer'
import { aiApi, mediaApi } from '@/services/api'
import type { AiTags, MediaEntry } from '@/services/types'
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
const { play, pause, activeUrl, isPlaying, progress } = usePlayer()

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

// AI panel
const showAiPanel = ref(false)
const aiEntry = ref<MediaEntry | null>(null)
const aiRunning = ref(false)
const aiResult = ref('')
const aiResultHtml = computed(() => (aiResult.value ? (marked.parse(aiResult.value) as string) : ''))
const aiTags = ref<AiTags | null>(null)
const aiError = ref('')
const aiSaved = ref('')
const aiTranslateLang = ref('French')

const AI_TRANSLATE_LANGUAGES = [
  'French', 'Spanish', 'Portuguese', 'German', 'Italian',
  'Dutch', 'Russian', 'Japanese', 'Chinese', 'Korean',
  'Arabic', 'Hindi', 'Polish', 'Swedish', 'Turkish', 'English',
] as const

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

/** True when the AI panel entry is a .md transcript file. */
const aiEntryIsTranscript = computed(() => aiEntry.value?.name.endsWith('.md') ?? false)

/** True when the AI panel entry is an audio file. */
const aiEntryIsAudio = computed(() => aiEntry.value?.mime.startsWith('audio/') ?? false)

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

// ── Melody extraction ─────────────────────────────────────────────────────────

function goToMelody(entry: MediaEntry): void {
  router.push({ name: 'Melody', query: { path: entry.rel_path } })
}

// ── AI panel ─────────────────────────────────────────────────────────────────

function openAiPanel(entry: MediaEntry): void {
  aiEntry.value = entry
  aiResult.value = ''
  aiTags.value = null
  aiError.value = ''
  aiSaved.value = ''
  showAiPanel.value = true
}

function closeAiPanel(): void {
  showAiPanel.value = false
  aiEntry.value = null
  aiResult.value = ''
  aiTags.value = null
  aiError.value = ''
  aiSaved.value = ''
  aiTranslateLang.value = 'French'
}

async function runAiTags(save: boolean): Promise<void> {
  if (!aiEntry.value) return
  aiRunning.value = true
  aiResult.value = ''
  aiTags.value = null
  aiError.value = ''
  aiSaved.value = ''
  try {
    const { data } = await aiApi.tags(aiEntry.value.rel_path, save)
    aiTags.value = data.tags
    if (save && data.saved_path) {
      aiSaved.value = t('ai.saved_ok', { path: data.saved_path })
      await loadDirectory(currentReqPath())
    }
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    aiError.value = msg ?? t('ai.error_generic')
  } finally {
    aiRunning.value = false
  }
}

async function runAiCleanup(save: boolean): Promise<void> {
  if (!aiEntry.value) return
  aiRunning.value = true
  aiResult.value = ''
  aiTags.value = null
  aiError.value = ''
  aiSaved.value = ''
  try {
    const { data } = await aiApi.cleanup(aiEntry.value.rel_path, save)
    aiResult.value = data.cleaned
    if (save) {
      aiSaved.value = t('ai.saved_ok', { path: aiEntry.value.rel_path })
      await loadDirectory(currentReqPath())
    }
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    aiError.value = msg ?? t('ai.error_generic')
  } finally {
    aiRunning.value = false
  }
}

async function runAiTranslate(save: boolean): Promise<void> {
  if (!aiEntry.value) return
  aiRunning.value = true
  aiResult.value = ''
  aiTags.value = null
  aiError.value = ''
  aiSaved.value = ''
  try {
    const { data } = await aiApi.translate(aiEntry.value.rel_path, aiTranslateLang.value, save)
    aiResult.value = data.translation
    if (save && data.saved_path) {
      aiSaved.value = t('ai.saved_ok', { path: data.saved_path })
      await loadDirectory(currentReqPath())
    }
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    aiError.value = msg ?? t('ai.error_generic')
  } finally {
    aiRunning.value = false
  }
}

async function runAiAnalyse(save: boolean): Promise<void> {
  if (!aiEntry.value) return
  aiRunning.value = true
  aiResult.value = ''
  aiTags.value = null
  aiError.value = ''
  aiSaved.value = ''
  try {
    const { data } = await aiApi.analyse(aiEntry.value.rel_path, save)
    aiResult.value = data.analysis
    if (save && data.saved_path) {
      aiSaved.value = t('ai.saved_ok', { path: data.saved_path })
      await loadDirectory(currentReqPath())
    }
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    aiError.value = msg ?? t('ai.error_generic')
  } finally {
    aiRunning.value = false
  }
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
                        @click="isActive(entry) && isPlaying ? pause() : playEntry(entry)"
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
                      :title="t('media.transcribe_title')"
                    >
                      <span v-if="transcribeRunning === entry.rel_path" class="spinner-border spinner-border-sm"></span>
                      <i v-else class="bi bi-mic"></i>
                    </button>

                    <!-- Extract Melody (audio only, hidden for viewer) -->
                    <button
                      v-if="entry.mime.startsWith('audio/') && !auth.isViewer"
                      class="btn btn-sm btn-outline-primary"
                      @click="goToMelody(entry)"
                      :title="t('media.melody_title')"
                    >
                      <i class="bi bi-music-note-list"></i>
                    </button>

                    <!-- AI panel (audio + .md files, hidden for viewer) -->
                    <button
                      v-if="(entry.mime.startsWith('audio/') || entry.name.endsWith('.md')) && !auth.isViewer"
                      class="btn btn-sm btn-outline-warning"
                      @click="openAiPanel(entry)"
                      :title="t('ai.btn_title')"
                    >
                      <i class="bi bi-stars"></i>
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

  <!-- AI panel modal -->
  <div
    v-if="showAiPanel && aiEntry"
    class="modal-overlay md-viewer-overlay position-fixed top-0 start-0 w-100 h-100 d-flex align-items-start justify-content-center pt-5"
    @click.self="closeAiPanel"
  >
    <div class="card border-0 shadow-lg md-viewer-card">
      <!-- Header -->
      <div class="card-header d-flex align-items-center justify-content-between py-2">
        <strong class="small text-truncate me-3">
          <i class="bi bi-stars text-warning me-1"></i>
          {{ t('ai.panel_title') }} — {{ aiEntry.name }}
        </strong>
        <button class="btn btn-sm btn-outline-secondary" @click="closeAiPanel">
          {{ t('common.close') }}
        </button>
      </div>

      <!-- Action buttons -->
      <div class="card-body border-bottom pb-3">
        <div class="d-flex flex-wrap gap-2">
          <!-- Clean Transcript — only for .md files -->
          <template v-if="aiEntryIsTranscript">
            <button
              class="btn btn-sm btn-outline-primary"
              :disabled="aiRunning"
              @click="runAiCleanup(false)"
            >
              <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
              <i v-else class="bi bi-magic me-1"></i>
              {{ t('ai.cleanup_btn') }}
            </button>
            <button
              class="btn btn-sm btn-primary"
              :disabled="aiRunning"
              @click="runAiCleanup(true)"
            >
              <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
              <i v-else class="bi bi-magic me-1"></i>
              {{ t('ai.cleanup_save_btn') }}
            </button>
          </template>

          <!-- Analyse Song — audio files + .md files -->
          <button
            class="btn btn-sm btn-outline-warning"
            :disabled="aiRunning"
            @click="runAiAnalyse(false)"
          >
            <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-bar-chart-line me-1"></i>
            {{ t('ai.analyse_btn') }}
          </button>
          <button
            class="btn btn-sm btn-warning"
            :disabled="aiRunning"
            @click="runAiAnalyse(true)"
          >
            <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-bar-chart-line me-1"></i>
            {{ t('ai.analyse_save_btn') }}
          </button>

          <!-- Divider -->
          <div class="vr mx-1"></div>

          <!-- Generate Tags — audio files + .md files -->
          <button
            class="btn btn-sm btn-outline-success"
            :disabled="aiRunning"
            @click="runAiTags(false)"
          >
            <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-tags me-1"></i>
            {{ t('ai.tags_btn') }}
          </button>
          <button
            class="btn btn-sm btn-success"
            :disabled="aiRunning"
            @click="runAiTags(true)"
          >
            <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-tags me-1"></i>
            {{ t('ai.tags_save_btn') }}
          </button>
        </div>

        <!-- Translate row (audio + .md files — needs transcript) -->
        <div class="d-flex flex-wrap align-items-center gap-2 mt-2 pt-2 border-top">
          <label class="small fw-semibold text-muted mb-0">
            <i class="bi bi-translate me-1"></i>{{ t('ai.translate_lang_label') }}
          </label>
          <select
            v-model="aiTranslateLang"
            class="form-select form-select-sm ai-lang-select"
            :disabled="aiRunning"
          >
            <option v-for="lang in AI_TRANSLATE_LANGUAGES" :key="lang" :value="lang">{{ lang }}</option>
          </select>
          <button
            class="btn btn-sm btn-outline-secondary"
            :disabled="aiRunning"
            @click="runAiTranslate(false)"
          >
            <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-translate me-1"></i>
            {{ t('ai.translate_btn') }}
          </button>
          <button
            class="btn btn-sm btn-secondary"
            :disabled="aiRunning"
            @click="runAiTranslate(true)"
          >
            <span v-if="aiRunning" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-translate me-1"></i>
            {{ t('ai.translate_save_btn') }}
          </button>
        </div>

        <!-- Running state hint -->
        <p v-if="aiRunning" class="text-muted small mt-2 mb-0">
          <span class="spinner-border spinner-border-sm me-1"></span>{{ t('ai.running') }}
        </p>

        <!-- Error -->
        <div v-if="aiError" class="alert alert-danger mt-3 mb-0 py-2 small">
          <i class="bi bi-exclamation-circle me-1"></i>{{ aiError }}
        </div>

        <!-- Saved confirmation -->
        <div v-if="aiSaved" class="alert alert-success mt-3 mb-0 py-2 small">
          <i class="bi bi-check-circle me-1"></i>{{ aiSaved }}
        </div>
      </div>

      <!-- Result -->
      <div class="card-body overflow-auto md-viewer-body">
        <!-- Empty state -->
        <div v-if="!aiResult && !aiTags && !aiRunning && !aiError" class="text-muted text-center py-4 small">
          {{ t('ai.result_placeholder') }}
        </div>

        <!-- Markdown result (cleanup / analyse) -->
        <div v-else-if="aiResult" class="doc-preview" v-html="aiResultHtml"></div>

        <!-- Structured tags result -->
        <div v-else-if="aiTags" class="ai-tags-result">
          <!-- Language + Energy + Tempo pills -->
          <div class="d-flex flex-wrap gap-2 mb-3">
            <span class="badge bg-secondary">
              <i class="bi bi-translate me-1"></i>{{ aiTags.language }}
            </span>
            <span
              class="badge"
              :class="{
                'bg-success': aiTags.energy === 'low',
                'bg-warning text-dark': aiTags.energy === 'medium',
                'bg-danger': aiTags.energy === 'high',
              }"
            >
              <i class="bi bi-lightning-charge me-1"></i>{{ t('ai.energy_label') }}: {{ aiTags.energy }}
            </span>
            <span class="badge bg-secondary">
              <i class="bi bi-speedometer2 me-1"></i>{{ t('ai.tempo_label') }}: {{ aiTags.tempo }}
            </span>
          </div>

          <!-- Genre -->
          <div class="mb-2">
            <span class="small fw-semibold text-muted me-2">{{ t('ai.genre_label') }}</span>
            <span v-for="g in aiTags.genre" :key="g" class="badge bg-primary me-1">{{ g }}</span>
          </div>

          <!-- Mood -->
          <div class="mb-2">
            <span class="small fw-semibold text-muted me-2">{{ t('ai.mood_label') }}</span>
            <span v-for="m in aiTags.mood" :key="m" class="badge bg-info text-dark me-1">{{ m }}</span>
          </div>

          <!-- Themes -->
          <div class="mb-2">
            <span class="small fw-semibold text-muted me-2">{{ t('ai.themes_label') }}</span>
            <span v-for="th in aiTags.themes" :key="th" class="badge bg-warning text-dark me-1">{{ th }}</span>
          </div>

          <!-- Instruments -->
          <div class="mb-3">
            <span class="small fw-semibold text-muted me-2">{{ t('ai.instruments_label') }}</span>
            <span v-for="ins in aiTags.instruments" :key="ins" class="badge bg-dark me-1">{{ ins }}</span>
          </div>

          <!-- All tags -->
          <div class="border-top pt-3">
            <p class="small fw-semibold text-muted mb-2">{{ t('ai.tags_all_label') }}</p>
            <div class="d-flex flex-wrap gap-1">
              <span v-for="tag in aiTags.tags" :key="tag" class="badge bg-light text-dark border">{{ tag }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

</template>
