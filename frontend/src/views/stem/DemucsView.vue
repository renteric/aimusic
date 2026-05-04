<script setup lang="ts">
/**
 * DemucsView.vue - Demucs stem separation page for AI-Music.
 *
 * Allows admins to upload an audio file, select a Demucs model and stems,
 * start a separation job, track progress, and download extracted stems.
 */

import DeviceBanner from '@/components/DeviceBanner.vue'
import { stemApi } from '@/services/api'
import type { StemJob, StemModelsResponse } from '@/services/types'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// ── State ─────────────────────────────────────────────────────────────────────

const modelsData = ref<StemModelsResponse | null>(null)
const selectedModel = ref<string>('htdemucs')
const selectedStems = ref<string[]>([])
const outputFormat = ref<'mp3' | 'wav'>('mp3')

const selectedFile = ref<File | null>(null)
const isDragging = ref(false)

const job = ref<StemJob | null>(null)
const jobError = ref('')
const isSubmitting = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

// ── Computed ──────────────────────────────────────────────────────────────────

const currentModelStems = computed(() => {
  if (!modelsData.value || !selectedModel.value) return []
  return modelsData.value.models[selectedModel.value]?.stems ?? []
})

const stemDefs = computed(() => modelsData.value?.stems ?? {})

const canSubmit = computed(
  () => selectedFile.value !== null && !isSubmitting.value && job.value?.status !== 'processing',
)

const jobDone = computed(() => job.value?.status === 'done')
const jobFailed = computed(() => job.value?.status === 'failed')

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  try {
    const { data } = await stemApi.models()
    modelsData.value = data
    selectedModel.value = data.default
    selectedStems.value = [...(data.models[data.default]?.stems ?? [])]
  } catch {
    jobError.value = 'Failed to load models. Is the separator service running?'
  }
})

// ── File handling ──────────────────────────────────────────────────────────────

function onFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.[0]) setFile(input.files[0])
}

function onDrop(e: DragEvent) {
  isDragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) setFile(file)
}

function setFile(file: File) {
  selectedFile.value = file
  job.value = null
  jobError.value = ''
}

function removeFile() {
  selectedFile.value = null
  job.value = null
  jobError.value = ''
}

// ── Model change ───────────────────────────────────────────────────────────────

function onModelChange() {
  selectedStems.value = [...currentModelStems.value]
}

function toggleStem(stemId: string) {
  const idx = selectedStems.value.indexOf(stemId)
  if (idx === -1) selectedStems.value.push(stemId)
  else selectedStems.value.splice(idx, 1)
}

// ── Job submission ─────────────────────────────────────────────────────────────

async function submit() {
  if (!selectedFile.value) return
  isSubmitting.value = true
  jobError.value = ''
  job.value = null
  stopPoll()

  try {
    const { data } = await stemApi.separateDemucs(
      selectedFile.value,
      selectedModel.value,
      selectedStems.value,
    )
    startPoll(data.job_id)
  } catch (err: any) {
    jobError.value = err.response?.data?.detail ?? 'Failed to start job.'
    isSubmitting.value = false
  }
}

function startPoll(jobId: string) {
  pollTimer = setInterval(async () => {
    try {
      const { data } = await stemApi.getJob(jobId)
      job.value = data
      if (data.status === 'done' || data.status === 'failed') {
        stopPoll()
        isSubmitting.value = false
      }
    } catch {
      stopPoll()
      isSubmitting.value = false
    }
  }, 1500)
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ── Downloads ─────────────────────────────────────────────────────────────────

function downloadStem(stemName: string) {
  if (!job.value) return
  window.location.href = stemApi.downloadStemUrl(job.value.job_id, stemName)
}

function downloadAll() {
  if (!job.value) return
  window.location.href = stemApi.downloadAllUrl(job.value.job_id)
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

function streamUrl(relPath: string): string {
  return `/api/media/stream/${relPath}`
}
</script>

<template>
  <div class="container py-4">
    <h2 class="mb-1 fw-bold"><span class="me-2">🎛️</span>{{ t('stem.demucs_title') }}</h2>
    <p class="text-muted mb-3">{{ t('stem.demucs_subtitle') }}</p>

    <!-- Device banner -->
    <DeviceBanner />

    <!-- Error banner -->
    <div v-if="jobError" class="alert alert-danger alert-dismissible" role="alert">
      {{ jobError }}
      <button type="button" class="btn-close" @click="jobError = ''"></button>
    </div>

    <!-- Upload card -->
    <div class="card mb-3">
      <div class="card-body">
        <h5 class="card-title mb-3">📂 {{ t('stem.upload_title') }}</h5>

        <div
          v-if="!selectedFile"
          class="border rounded-3 p-5 text-center cursor-pointer"
          :class="isDragging ? 'border-primary bg-primary bg-opacity-10' : 'border-secondary'"
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop.prevent="onDrop"
          @click="($refs.fileInput as HTMLInputElement).click()"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".mp3,.wav,.flac,.ogg,.m4a,.aac"
            class="d-none"
            @change="onFileInput"
          />
          <div class="fs-1 mb-2">🎧</div>
          <div class="fw-semibold">{{ t('stem.drop_here') }}</div>
          <div class="text-muted small">{{ t('stem.drop_hint') }}</div>
        </div>

        <div v-else class="d-flex align-items-center gap-3 p-3 border rounded-3">
          <div class="fs-2">🎵</div>
          <div class="flex-grow-1">
            <div class="fw-semibold">{{ selectedFile.name }}</div>
            <div class="text-muted small">{{ formatBytes(selectedFile.size) }}</div>
          </div>
          <button class="btn btn-sm btn-outline-danger" @click="removeFile">✕</button>
        </div>
      </div>
    </div>

    <!-- Options card -->
    <div v-if="modelsData" class="card mb-3">
      <div class="card-body">
        <h5 class="card-title mb-3">⚙️ {{ t('stem.options_title') }}</h5>

        <div class="row g-3 mb-3">
          <div class="col-md-6">
            <label class="form-label">{{ t('stem.model_label') }}</label>
            <select v-model="selectedModel" class="form-select" @change="onModelChange">
              <option v-for="(info, id) in modelsData.models" :key="id" :value="id">
                {{ id }} — {{ info.quality }}
              </option>
            </select>
          </div>
          <div class="col-md-6">
            <label class="form-label">{{ t('stem.output_format_label') }}</label>
            <select v-model="outputFormat" class="form-select">
              <option value="mp3">{{ t('stem.format_mp3') }}</option>
              <option value="wav">{{ t('stem.format_wav') }}</option>
            </select>
          </div>
        </div>

        <div class="mb-2 fw-semibold small">{{ t('stem.select_stems_label') }}</div>
        <div class="d-flex flex-wrap gap-2">
          <button
            v-for="stemId in currentModelStems"
            :key="stemId"
            type="button"
            class="btn btn-sm"
            :class="selectedStems.includes(stemId) ? 'btn-primary' : 'btn-outline-secondary'"
            @click="toggleStem(stemId)"
          >
            <span
              class="stem-dot-sm me-1"
              :style="{ background: stemDefs[stemId]?.color ?? '#999' }"
            ></span>
            {{ stemDefs[stemId]?.label ?? stemId }}
          </button>
        </div>
      </div>
    </div>

    <!-- Submit button -->
    <button
      class="btn btn-primary btn-lg mb-4"
      :disabled="!canSubmit"
      @click="submit"
    >
      <span v-if="isSubmitting" class="spinner-border spinner-border-sm me-2"></span>
      🎛️ {{ t('stem.separate_btn') }}
    </button>

    <!-- Progress card -->
    <div v-if="job && (job.status === 'queued' || job.status === 'processing')" class="card mb-3">
      <div class="card-body">
        <h5 class="card-title">⏳ {{ t('stem.processing_title') }}</h5>
        <div class="d-flex align-items-center gap-2 mb-2">
          <div class="spinner-border spinner-border-sm text-primary"></div>
          <span class="text-muted small">{{ job.message }}</span>
        </div>
        <div class="progress progress-sm mb-1">
          <div
            class="progress-bar progress-bar-striped progress-bar-animated"
            :style="`width:${job.progress}%`"
          ></div>
        </div>
        <div class="text-muted small">{{ job.progress }}%</div>
      </div>
    </div>

    <!-- Results card -->
    <div v-if="jobDone && job" class="card mb-3 border-success">
      <div class="card-body">
        <div class="d-flex align-items-center justify-content-between mb-3">
          <h5 class="card-title mb-0 text-success">✅ {{ t('stem.extracted_title') }}</h5>
          <div class="d-flex gap-2">
            <button class="btn btn-sm btn-outline-primary" @click="downloadAll">
              ⬇ {{ t('stem.download_all_btn') }}
            </button>
          </div>
        </div>

        <div class="list-group">
          <div
            v-for="(filename, stemName) in job.stems_produced"
            :key="stemName"
            class="list-group-item d-flex align-items-center gap-3"
          >
            <span
              class="stem-dot"
              :style="{ background: stemDefs[stemName]?.color ?? '#999' }"
            ></span>
            <div class="flex-grow-1">
              <div class="fw-semibold">{{ stemDefs[stemName]?.label ?? stemName }}</div>
              <div class="text-muted small">{{ filename }}</div>
            </div>
            <audio
              :src="streamUrl(`stems/${encodeURIComponent(job.filename.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9 \-_.]/g, '').trim())}/${filename}`)"
              controls
              class="flex-shrink-0 stem-mini-player"
            ></audio>
            <button class="btn btn-sm btn-outline-secondary" @click="downloadStem(stemName)">
              ⬇
            </button>
          </div>
        </div>

        <div v-if="job.duration_s" class="text-muted small mt-2">
          {{ t('stem.completed_in', { s: job.duration_s }) }}
        </div>
      </div>
    </div>

    <!-- Failed card -->
    <div v-if="jobFailed && job" class="card mb-3 border-danger">
      <div class="card-body">
        <h5 class="card-title text-danger">❌ {{ t('stem.failed_title') }}</h5>
        <p class="mb-0 text-muted">{{ job.error ?? 'Unknown error.' }}</p>
      </div>
    </div>
  </div>
</template>
