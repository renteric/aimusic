<script setup lang="ts">
/**
 * MelodyView.vue - Melody extraction UI.
 *
 * Accepts an audio file path (pre-filled from ?path= query param when
 * navigated from the media browser), optional extraction parameters, and
 * drives the /api/melody/extract → /api/melody/jobs/{id} job lifecycle with
 * live polling.
 */

import { melodyApi } from '@/services/api'
import type { MelodyJob } from '@/services/types'
import { useAuthStore } from '@/stores/auth'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

const auth = useAuthStore()
const { t } = useI18n()
const route = useRoute()

// ── Form state ────────────────────────────────────────────────────────────────

const filePath = ref('')
const fmin = ref('C4')
const fmax = ref('A6')
const minNoteMs = ref(60)
const useHpss = ref(true)
const bpmOverride = ref<number | null>(null)
const keyOverride = ref('')
const modeOverride = ref('')
const harmonyMode = ref('diatonic')

const showAdvanced = ref(false)
const submitting = ref(false)
const formError = ref('')

// ── Job state ─────────────────────────────────────────────────────────────────

const job = ref<MelodyJob | null>(null)
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)

// Save-to-library state
const savingAll = ref(false)
const savingFile = ref<string | null>(null)  // filename currently being saved
const savedPaths = ref<Record<string, string>>({})  // filename → saved rel_path
const saveAllPaths = ref<string[]>([])
const saveError = ref('')

// ── Computed ──────────────────────────────────────────────────────────────────

const isProcessing = computed(
  () => job.value?.status === 'pending' || job.value?.status === 'processing',
)
const isDone = computed(() => job.value?.status === 'done')
const isFailed = computed(() => job.value?.status === 'failed')

const keyBadge = computed(() => {
  if (!job.value?.summary) return ''
  return `${job.value.summary.key} ${job.value.summary.mode}`
})

const bpmBadge = computed(() => {
  if (!job.value?.summary) return ''
  return `${job.value.summary.bpm.toFixed(1)} BPM`
})

const downloadFiles = computed((): { filename: string; label: string; icon: string }[] => {
  if (!job.value || !job.value.outputs.length) return []
  const map: Record<string, { label: string; icon: string }> = {
    'melody.mid': { label: t('melody.dl_melody_midi'), icon: 'bi-file-earmark-music' },
    'duet.mid': { label: t('melody.dl_duet_midi'), icon: 'bi-file-earmark-music' },
    'lead_sheet.musicxml': { label: t('melody.dl_musicxml'), icon: 'bi-file-earmark-text' },
    'notes.csv': { label: t('melody.dl_csv'), icon: 'bi-file-earmark-spreadsheet' },
    'summary.json': { label: t('melody.dl_summary'), icon: 'bi-file-earmark-code' },
  }
  return job.value.outputs
    .filter((f) => map[f])
    .map((f) => ({ filename: f, ...map[f] }))
})

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(() => {
  // Pre-fill path from query param (set by "Extract Melody" button in media browser)
  const qpath = route.query.path
  if (qpath && typeof qpath === 'string') {
    filePath.value = qpath
  }
})

onUnmounted(() => {
  stopPolling()
})

// ── Polling ───────────────────────────────────────────────────────────────────

function startPolling(jobId: string): void {
  stopPolling()
  pollingTimer.value = setInterval(async () => {
    try {
      const { data } = await melodyApi.getJob(jobId)
      job.value = data
      if (data.status === 'done' || data.status === 'failed') {
        stopPolling()
      }
    } catch {
      stopPolling()
    }
  }, 2000)
}

function stopPolling(): void {
  if (pollingTimer.value !== null) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

// ── Submission ────────────────────────────────────────────────────────────────

async function handleSubmit(): Promise<void> {
  if (!filePath.value.trim()) {
    formError.value = t('melody.error_no_path')
    return
  }
  if (keyOverride.value && !modeOverride.value) {
    formError.value = t('melody.error_key_mode')
    return
  }
  if (modeOverride.value && !keyOverride.value) {
    formError.value = t('melody.error_key_mode')
    return
  }

  formError.value = ''
  submitting.value = true
  job.value = null

  try {
    const { data } = await melodyApi.extract(filePath.value.trim(), {
      fmin: fmin.value,
      fmax: fmax.value,
      min_note_ms: minNoteMs.value,
      use_hpss: useHpss.value,
      bpm: bpmOverride.value || null,
      key: keyOverride.value || null,
      mode: modeOverride.value || null,
      harmony_mode: harmonyMode.value,
    })
    // Bootstrap the job object immediately so the UI shows "pending"
    job.value = {
      job_id: data.job_id,
      status: data.status,
      audio_path: filePath.value.trim(),
      audio_name: filePath.value.trim().split('/').pop() ?? filePath.value.trim(),
      started_at: Date.now() / 1000,
      error: '',
      outputs: [],
    }
    startPolling(data.job_id)
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    formError.value = msg ?? t('common.request_failed')
  } finally {
    submitting.value = false
  }
}

async function handleDelete(): Promise<void> {
  if (!job.value) return
  try {
    await melodyApi.deleteJob(job.value.job_id)
    job.value = null
  } catch {
    // ignore
  }
}

async function handleSaveFile(filename: string): Promise<void> {
  if (!job.value) return
  savingFile.value = filename
  saveError.value = ''
  try {
    const { data } = await melodyApi.saveFile(job.value.job_id, filename)
    savedPaths.value = { ...savedPaths.value, [filename]: data.saved }
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    saveError.value = msg ?? t('common.request_failed')
  } finally {
    savingFile.value = null
  }
}

async function handleSaveAll(): Promise<void> {
  if (!job.value) return
  savingAll.value = true
  saveError.value = ''
  saveAllPaths.value = []
  try {
    const { data } = await melodyApi.saveAll(job.value.job_id)
    saveAllPaths.value = data.saved
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    saveError.value = msg ?? t('common.request_failed')
  } finally {
    savingAll.value = false
  }
}

function resetForm(): void {
  job.value = null
  formError.value = ''
  savedPaths.value = {}
  saveAllPaths.value = []
  saveError.value = ''
}
</script>

<template>
  <div class="container py-4">

    <!-- Header -->
    <div class="mb-4">
      <h2 class="mb-0 fw-bold">
        <i class="bi bi-music-note-list me-2 text-primary"></i>{{ t('melody.title') }}
      </h2>
      <p class="text-muted small mb-0">{{ t('melody.subtitle') }}</p>
    </div>

    <!-- Viewer role lock -->
    <div v-if="auth.isViewer" class="alert alert-warning">
      <i class="bi bi-lock me-1"></i>{{ t('melody.viewer_locked') }}
    </div>

    <template v-else>

      <!-- ── Extract form ─────────────────────────────────────────────────── -->
      <div class="card border-0 shadow-sm mb-4">
        <div class="card-header py-2">
          <strong class="small"><i class="bi bi-music-note-beamed me-1"></i>{{ t('melody.form_title') }}</strong>
        </div>
        <div class="card-body">

          <!-- File path -->
          <div class="mb-3">
            <label class="form-label small fw-semibold">{{ t('melody.path_label') }}</label>
            <input
              v-model="filePath"
              type="text"
              class="form-control"
              :placeholder="t('melody.path_placeholder')"
              :disabled="submitting || isProcessing"
            />
            <div class="form-text">{{ t('melody.path_hint') }}</div>
          </div>

          <!-- Advanced options toggle -->
          <button
            class="btn btn-sm btn-link p-0 mb-3 text-decoration-none"
            type="button"
            @click="showAdvanced = !showAdvanced"
          >
            <i :class="['bi me-1', showAdvanced ? 'bi-chevron-up' : 'bi-chevron-down']"></i>
            {{ t('melody.advanced_toggle') }}
          </button>

          <!-- Advanced options -->
          <div v-if="showAdvanced" class="border rounded p-3 mb-3 bg-light">
            <div class="row g-3">

              <!-- fmin -->
              <div class="col-6 col-md-3">
                <label class="form-label small">{{ t('melody.fmin_label') }}</label>
                <input
                  v-model="fmin"
                  type="text"
                  class="form-control form-control-sm"
                  placeholder="C4"
                  :disabled="submitting || isProcessing"
                />
              </div>

              <!-- fmax -->
              <div class="col-6 col-md-3">
                <label class="form-label small">{{ t('melody.fmax_label') }}</label>
                <input
                  v-model="fmax"
                  type="text"
                  class="form-control form-control-sm"
                  placeholder="A6"
                  :disabled="submitting || isProcessing"
                />
              </div>

              <!-- BPM override -->
              <div class="col-6 col-md-3">
                <label class="form-label small">{{ t('melody.bpm_label') }}</label>
                <input
                  v-model.number="bpmOverride"
                  type="number"
                  min="40"
                  max="300"
                  step="1"
                  class="form-control form-control-sm"
                  :placeholder="t('melody.auto')"
                  :disabled="submitting || isProcessing"
                />
              </div>

              <!-- Min note ms -->
              <div class="col-6 col-md-3">
                <label class="form-label small">{{ t('melody.min_note_label') }}</label>
                <input
                  v-model.number="minNoteMs"
                  type="number"
                  min="20"
                  max="500"
                  step="10"
                  class="form-control form-control-sm"
                  :disabled="submitting || isProcessing"
                />
              </div>

              <!-- Key override -->
              <div class="col-6 col-md-3">
                <label class="form-label small">{{ t('melody.key_label') }}</label>
                <input
                  v-model="keyOverride"
                  type="text"
                  class="form-control form-control-sm"
                  :placeholder="t('melody.auto')"
                  :disabled="submitting || isProcessing"
                />
              </div>

              <!-- Mode override -->
              <div class="col-6 col-md-3">
                <label class="form-label small">{{ t('melody.mode_label') }}</label>
                <select
                  v-model="modeOverride"
                  class="form-select form-select-sm"
                  :disabled="submitting || isProcessing"
                >
                  <option value="">{{ t('melody.auto') }}</option>
                  <option value="major">major</option>
                  <option value="minor">minor</option>
                </select>
              </div>

              <!-- Harmony mode -->
              <div class="col-6 col-md-3">
                <label class="form-label small">{{ t('melody.harmony_label') }}</label>
                <select
                  v-model="harmonyMode"
                  class="form-select form-select-sm"
                  :disabled="submitting || isProcessing"
                >
                  <option value="diatonic">diatonic</option>
                  <option value="fixed+3">fixed +3</option>
                </select>
              </div>

              <!-- HPSS toggle -->
              <div class="col-12 col-md-3 d-flex align-items-end">
                <div class="form-check mb-1">
                  <input
                    id="chk-hpss"
                    v-model="useHpss"
                    type="checkbox"
                    class="form-check-input"
                    :disabled="submitting || isProcessing"
                  />
                  <label for="chk-hpss" class="form-check-label small">{{ t('melody.hpss_label') }}</label>
                </div>
              </div>
            </div>
          </div>

          <!-- Form error -->
          <div v-if="formError" class="alert alert-danger py-2 small mb-3">
            <i class="bi bi-exclamation-circle me-1"></i>{{ formError }}
          </div>

          <!-- Submit -->
          <button
            class="btn btn-primary"
            :disabled="submitting || isProcessing"
            @click="handleSubmit"
          >
            <span v-if="submitting || isProcessing" class="spinner-border spinner-border-sm me-2"></span>
            <i v-else class="bi bi-play-fill me-1"></i>
            {{ submitting || isProcessing ? t('melody.extracting') : t('melody.extract_btn') }}
          </button>
        </div>
      </div>

      <!-- ── Job result ───────────────────────────────────────────────────── -->
      <div v-if="job" class="card border-0 shadow-sm">
        <div class="card-header d-flex align-items-center justify-content-between py-2">
          <strong class="small">
            <i class="bi bi-activity me-1"></i>{{ t('melody.result_title') }}
            <span class="text-muted ms-1">— {{ job.audio_name }}</span>
          </strong>
          <div class="d-flex gap-2">
            <!-- Status badge -->
            <span
              class="badge"
              :class="{
                'bg-secondary': job.status === 'pending',
                'bg-warning text-dark': job.status === 'processing',
                'bg-success': job.status === 'done',
                'bg-danger': job.status === 'failed',
              }"
            >{{ job.status }}</span>
            <!-- Delete button (done/failed only) -->
            <button
              v-if="!isProcessing"
              class="btn btn-sm btn-outline-secondary"
              @click="handleDelete"
            >
              <i class="bi bi-trash"></i>
            </button>
          </div>
        </div>

        <div class="card-body">

          <!-- Processing state -->
          <div v-if="isProcessing" class="text-center py-5">
            <div class="spinner-border text-primary mb-3"></div>
            <p class="text-muted mb-1">{{ t('melody.processing_hint') }}</p>
            <p class="text-muted small">{{ t('melody.processing_hint2') }}</p>
          </div>

          <!-- Done state -->
          <div v-else-if="isDone && job.summary">
            <!-- Key metrics badges -->
            <div class="d-flex flex-wrap gap-2 mb-4">
              <span class="badge bg-primary fs-6 px-3 py-2">
                <i class="bi bi-speedometer2 me-1"></i>{{ bpmBadge }}
              </span>
              <span class="badge bg-success fs-6 px-3 py-2">
                <i class="bi bi-music-note me-1"></i>{{ keyBadge }}
              </span>
              <span class="badge bg-info text-dark fs-6 px-3 py-2">
                <i class="bi bi-list-ol me-1"></i>{{ job.summary.notes_count }} {{ t('melody.notes_label') }}
              </span>
              <span class="badge bg-secondary fs-6 px-3 py-2">
                <i class="bi bi-clock me-1"></i>{{ job.summary.duration_sec.toFixed(1) }}s
              </span>
            </div>

            <!-- Download / Save buttons -->
            <div>
              <!-- Header row: label + Download All ZIP + Save All -->
              <div class="d-flex align-items-center justify-content-between mb-2">
                <p class="small fw-semibold text-muted mb-0">
                  <i class="bi bi-download me-1"></i>{{ t('melody.downloads_label') }}
                </p>
                <div class="d-flex gap-2">
                  <a
                    :href="melodyApi.downloadAllUrl(job.job_id)"
                    class="btn btn-outline-primary btn-sm"
                    download
                  >
                    <i class="bi bi-file-zip me-1"></i>{{ t('melody.dl_all_zip') }}
                  </a>
                  <button
                    class="btn btn-primary btn-sm"
                    :disabled="savingAll"
                    @click="handleSaveAll"
                  >
                    <span v-if="savingAll" class="spinner-border spinner-border-sm me-1"></span>
                    <i v-else class="bi bi-folder-check me-1"></i>
                    {{ t('melody.save_all') }}
                  </button>
                </div>
              </div>

              <!-- Save-all success -->
              <div v-if="saveAllPaths.length" class="alert alert-success py-2 small mb-2">
                <i class="bi bi-check-circle me-1"></i>{{ t('melody.saved_ok') }}
                <ul class="mb-0 mt-1 ps-3">
                  <li v-for="p in saveAllPaths" :key="p">
                    <code>{{ p }}</code>
                  </li>
                </ul>
              </div>

              <!-- Save error -->
              <div v-if="saveError" class="alert alert-danger py-2 small mb-2">
                <i class="bi bi-exclamation-circle me-1"></i>{{ saveError }}
              </div>

              <!-- Per-file rows -->
              <div class="d-flex flex-column gap-1">
                <div
                  v-for="file in downloadFiles"
                  :key="file.filename"
                  class="d-flex align-items-center gap-2"
                >
                  <!-- Download -->
                  <a
                    :href="melodyApi.downloadUrl(job.job_id, file.filename)"
                    class="btn btn-outline-primary btn-sm"
                    download
                  >
                    <i :class="['bi me-1', file.icon]"></i>{{ file.label }}
                  </a>

                  <!-- Save to library -->
                  <button
                    class="btn btn-sm btn-outline-secondary"
                    :disabled="savingFile === file.filename || savingAll"
                    :title="t('melody.save_to_library')"
                    @click="handleSaveFile(file.filename)"
                  >
                    <span v-if="savingFile === file.filename" class="spinner-border spinner-border-sm"></span>
                    <i v-else class="bi bi-floppy"></i>
                  </button>

                  <!-- Saved path confirmation -->
                  <span v-if="savedPaths[file.filename]" class="text-success small">
                    <i class="bi bi-check-circle me-1"></i>
                    <code>{{ savedPaths[file.filename] }}</code>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Failed state -->
          <div v-else-if="isFailed">
            <div class="alert alert-danger mb-3">
              <i class="bi bi-x-circle me-2"></i>
              <strong>{{ t('melody.failed_title') }}</strong>
              <div class="mt-1 small">{{ job.error || t('melody.failed_unknown') }}</div>
            </div>
            <button class="btn btn-sm btn-outline-secondary" @click="resetForm">
              <i class="bi bi-arrow-counterclockwise me-1"></i>{{ t('melody.try_again') }}
            </button>
          </div>

        </div>
      </div>

    </template>
  </div>
</template>
