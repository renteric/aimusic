<script setup lang="ts">
/**
 * DownloadQueueView.vue - Download job queue manager.
 *
 * Polls /api/download/jobs every 3 seconds while any job is still running.
 * Allows dismissing completed/failed jobs from the list.
 */

import { cancelDownloadJob, listDownloadJobs, removeDownloadJob } from '@/services/api'
import type { DownloadJobSummary } from '@/services/types'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const jobs = ref<DownloadJobSummary[]>([])
const loading = ref(true)
const error = ref('')
const removing = ref<string | null>(null)
const stopping = ref<string | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null

const hasRunning = computed(() => jobs.value.some((j) => !j.done))

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`
  return `${(bytes / 1073741824).toFixed(2)} GB`
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

function shortDir(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/')
  return parts.slice(-2).join('/')
}

async function loadJobs(): Promise<void> {
  try {
    const { data } = await listDownloadJobs()
    jobs.value = data
    error.value = ''
  } catch {
    error.value = t('queue.error_load')
  } finally {
    loading.value = false
  }
}

async function handleStop(jobId: string): Promise<void> {
  stopping.value = jobId
  try {
    await cancelDownloadJob(jobId)
    await loadJobs()
  } catch {
    // ignore — job may have already finished
  } finally {
    stopping.value = null
  }
}

async function handleRemove(jobId: string): Promise<void> {
  removing.value = jobId
  try {
    await removeDownloadJob(jobId)
    jobs.value = jobs.value.filter((j) => j.job_id !== jobId)
  } catch {
    // ignore — job may already be gone
  } finally {
    removing.value = null
  }
}

function startPolling(): void {
  stopPolling()
  pollTimer = setInterval(async () => {
    await loadJobs()
    if (!hasRunning.value) stopPolling()
  }, 3000)
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(async () => {
  await loadJobs()
  if (hasRunning.value) startPolling()
})

onUnmounted(() => stopPolling())
</script>

<template>
  <div class="container py-4">

    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-4">
      <div>
        <h2 class="mb-0 fw-bold">
          <i class="bi bi-list-task me-2 text-primary"></i>{{ t('queue.title') }}
        </h2>
        <p class="text-muted small mb-0">{{ t('queue.subtitle') }}</p>
      </div>
      <button class="btn btn-outline-secondary btn-sm" @click="loadJobs">
        <i class="bi bi-arrow-clockwise me-1"></i>{{ t('queue.refresh') }}
      </button>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <!-- Loading -->
    <div v-else-if="loading" class="text-center py-5 text-muted">
      <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
    </div>

    <!-- Empty -->
    <div v-else-if="jobs.length === 0" class="card border-0 shadow-sm">
      <div class="card-body text-center py-5 text-muted">
        <i class="bi bi-inbox display-5 d-block mb-3"></i>
        {{ t('queue.empty') }}
      </div>
    </div>

    <!-- Job list -->
    <div v-else class="d-flex flex-column gap-3">
      <div
        v-for="job in jobs"
        :key="job.job_id"
        class="card border-0 shadow-sm"
      >
        <div class="card-header d-flex align-items-center justify-content-between py-2">
          <div class="d-flex align-items-center gap-2">
            <!-- Status badge -->
            <span
              class="badge"
              :class="{
                'bg-warning text-dark': !job.done,
                'bg-success': job.done && job.success,
                'bg-danger': job.done && !job.success,
              }"
            >
              <span v-if="!job.done" class="spinner-border spinner-border-sm me-1" style="width:.65rem;height:.65rem;"></span>
              {{ !job.done ? t('queue.running') : job.success ? t('queue.done') : t('queue.failed') }}
            </span>

            <!-- Post-processing badges -->
            <span v-if="job.auto_transcribe" class="badge bg-info text-dark">
              <i class="bi bi-mic me-1"></i>{{ t('queue.badge_transcribe') }}
            </span>
            <span v-if="job.auto_stem" class="badge bg-success">
              <i class="bi bi-layers me-1"></i>{{ t('queue.badge_stem') }}
            </span>

            <code class="small text-muted">{{ job.job_id.slice(0, 12) }}</code>
          </div>

          <div class="d-flex align-items-center gap-2">
            <span class="text-muted small">{{ formatTime(job.started_at) }}</span>
            <button
              v-if="!job.done"
              class="btn btn-sm btn-outline-danger"
              :disabled="stopping === job.job_id"
              :title="t('queue.stop')"
              @click="handleStop(job.job_id)"
            >
              <span v-if="stopping === job.job_id" class="spinner-border spinner-border-sm"></span>
              <i v-else class="bi bi-stop-circle"></i>
            </button>
            <button
              v-if="job.done"
              class="btn btn-sm btn-outline-secondary"
              :disabled="removing === job.job_id"
              :title="t('queue.remove')"
              @click="handleRemove(job.job_id)"
            >
              <span v-if="removing === job.job_id" class="spinner-border spinner-border-sm"></span>
              <i v-else class="bi bi-x-lg"></i>
            </button>
          </div>
        </div>

        <div class="card-body py-2">
          <!-- Output dir -->
          <div class="small text-muted mb-1">
            <i class="bi bi-folder me-1"></i>
            <code>{{ shortDir(job.output_dir) }}</code>
          </div>

          <!-- Success message -->
          <div v-if="job.done && job.success" class="small text-success">
            <i class="bi bi-check-circle me-1"></i>{{ job.message }}
          </div>

          <!-- Error -->
          <div v-if="job.done && !job.success && job.error" class="small text-danger">
            <i class="bi bi-exclamation-circle me-1"></i>{{ job.error }}
          </div>

          <!-- Running hint -->
          <div v-if="!job.done" class="small text-muted fst-italic">
            {{ t('queue.running_hint') }}
            <RouterLink :to="{ path: '/download' }" class="ms-1">{{ t('queue.view_logs') }}</RouterLink>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>
