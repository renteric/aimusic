<script setup lang="ts">
/**
 * AudioSepView.vue - AudioSep text-guided stem separation page for AI-Powered-Music.
 *
 * Allows admins to upload an audio file and select one or more predefined stems.
 * Each stem maps to a natural-language prompt sent to the AudioSep model, which
 * uses a text-audio neural network to isolate the described sound source.
 */

import DeviceBanner from '@/components/DeviceBanner.vue'
import { stemApi } from '@/services/api'
import type { StemJob } from '@/services/types'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// ── Stem definitions (mirrors AUDIOSEP_STEMS in separator/src/config/settings.py) ──

const AUDIOSEP_STEMS = [
  { id: 'vocals',      label: '🎤 Vocals',       prompt: 'human singing vocals',          color: '#e74c3c' },
  { id: 'drums',       label: '🥁 Drums',         prompt: 'drum kit playing',              color: '#e67e22' },
  { id: 'bass',        label: '🎸 Bass',           prompt: 'bass guitar playing',           color: '#8e44ad' },
  { id: 'guitar',      label: '🎸 Guitar',         prompt: 'electric guitar playing',       color: '#2ecc71' },
  { id: 'piano',       label: '🎹 Piano',          prompt: 'piano playing',                 color: '#3498db' },
  { id: 'synthesizer', label: '🎹 Synthesizer',    prompt: 'synthesizer playing',           color: '#9b59b6' },
  { id: 'strings',     label: '🎻 Strings',        prompt: 'string instruments playing',    color: '#1abc9c' },
  { id: 'brass',       label: '🎺 Brass',          prompt: 'brass instruments playing',     color: '#e74c3c' },
  { id: 'woodwinds',   label: '🎷 Woodwinds',      prompt: 'woodwind instruments playing',  color: '#f39c12' },
  { id: 'flute',       label: '🪈 Flute',          prompt: 'flute playing',                 color: '#27ae60' },
]

const stemDefs = computed(() =>
  Object.fromEntries(AUDIOSEP_STEMS.map((s) => [s.id, { label: s.label, color: s.color }])),
)

// ── State ─────────────────────────────────────────────────────────────────────

const selectedStems = ref<string[]>(['vocals'])

const selectedFile = ref<File | null>(null)
const isDragging = ref(false)

const job = ref<StemJob | null>(null)
const jobError = ref('')
const isSubmitting = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

// ── Computed ──────────────────────────────────────────────────────────────────

const canSubmit = computed(
  () =>
    selectedFile.value !== null &&
    selectedStems.value.length > 0 &&
    !isSubmitting.value &&
    job.value?.status !== 'processing',
)

const jobDone = computed(() => job.value?.status === 'done')
const jobFailed = computed(() => job.value?.status === 'failed')

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

// ── Stem toggles ───────────────────────────────────────────────────────────────

function toggleStem(stemId: string) {
  const idx = selectedStems.value.indexOf(stemId)
  if (idx === -1) selectedStems.value.push(stemId)
  else selectedStems.value.splice(idx, 1)
}

// ── Job submission ─────────────────────────────────────────────────────────────

async function submit() {
  if (!selectedFile.value || selectedStems.value.length === 0) return
  isSubmitting.value = true
  jobError.value = ''
  job.value = null
  stopPoll()

  try {
    const { data } = await stemApi.separateAudiosep(selectedFile.value, selectedStems.value)
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
    <h2 class="mb-1 fw-bold"><span class="me-2">🔊</span>{{ t('stem.audiosep_title') }}</h2>
    <p class="text-muted mb-3">{{ t('stem.audiosep_subtitle') }}</p>

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

    <!-- Stems card -->
    <div class="card mb-3">
      <div class="card-body">
        <h5 class="card-title mb-1">⚙️ {{ t('stem.select_stems_label') }}</h5>
        <p class="text-muted small mb-3">{{ t('stem.audiosep_stems_hint') }}</p>
        <div class="d-flex flex-wrap gap-2">
          <button
            v-for="stem in AUDIOSEP_STEMS"
            :key="stem.id"
            type="button"
            class="btn btn-sm"
            :class="selectedStems.includes(stem.id) ? 'btn-primary' : 'btn-outline-secondary'"
            :title="`Prompt: &quot;${stem.prompt}&quot;`"
            @click="toggleStem(stem.id)"
          >
            <span
              class="stem-dot-sm me-1"
              :style="{ background: stem.color }"
            ></span>
            {{ stem.label }}
          </button>
        </div>
        <div v-if="selectedStems.length === 0" class="text-danger small mt-2">
          {{ t('stem.select_stem_required') }}
        </div>
        <div v-if="selectedStems.length > 0" class="text-muted small mt-2">
          <span class="fw-semibold">{{ t('stem.audiosep_prompts_label') }}</span>
          {{ AUDIOSEP_STEMS.filter(s => selectedStems.includes(s.id)).map(s => `"${s.prompt}"`).join(' · ') }}
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
      🔊 {{ t('stem.extract_btn') }}
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
          <button class="btn btn-sm btn-outline-primary" @click="downloadAll">
            ⬇ Download All (ZIP)
          </button>
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
          Completed in {{ job.duration_s }}s
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
