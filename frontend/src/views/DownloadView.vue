<script setup lang="ts">
/**
 * DownloadView.vue - Audio download form with real-time log streaming.
 *
 * Fetches available formats/bitrates from /api/config on mount.
 * Verbose downloads open an SSE stream that appends log lines to a terminal
 * panel in real time. Multiple verbose jobs can run simultaneously; each
 * gets its own collapsible log panel.
 */

import { ref, computed, onMounted, reactive, nextTick } from 'vue'
import { fetchConfig, startDownload } from '@/services/api'
import { useI18n } from 'vue-i18n'
import type { JobDoneEvent } from '@/services/types'

const { t } = useI18n()

// ── State ─────────────────────────────────────────────────────────────────────

const formats = ref<string[]>(['mp3'])
const bitrates = ref<string[]>(['320k'])
const source = ref<'single' | 'playlist' | 'search_txt'>('single')
const url = ref('')
const searchTxt = ref('')
const format = ref('mp3')
const bitrate = ref('320k')
const output = ref('')
const verbose = ref(false)
const submitting = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

/** Log sessions for verbose downloads, newest first. */
interface LogSession {
  jobId: string
  lines: string[]
  done: boolean
  success: boolean | null
  hidden: boolean
}
const sessions = ref<LogSession[]>([])

/** Terminal element refs keyed by jobId, used for auto-scroll. */
const terminalRefs = new Map<string, HTMLPreElement>()
function setTermRef(jobId: string, el: Element | null): void {
  if (el) terminalRefs.set(jobId, el as HTMLPreElement)
  else terminalRefs.delete(jobId)
}

const isSearchMode = computed(() => source.value === 'search_txt')

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  try {
    const { data } = await fetchConfig()
    formats.value = data.formats
    bitrates.value = data.bitrates
  } catch {
    // Fall back to hardcoded defaults if config fetch fails.
  }
})

// ── Submit ────────────────────────────────────────────────────────────────────

/** Validate and submit the download form. */
async function handleSubmit(): Promise<void> {
  errorMsg.value = ''
  successMsg.value = ''

  if (!isSearchMode.value && !url.value.trim()) {
    errorMsg.value = t('download.error_url')
    return
  }
  if (isSearchMode.value && !searchTxt.value.trim()) {
    errorMsg.value = t('download.error_search')
    return
  }

  submitting.value = true
  try {
    const { data } = await startDownload({
      source: source.value,
      format: format.value,
      bitrate: bitrate.value,
      url: isSearchMode.value ? undefined : url.value.trim(),
      search_txt: isSearchMode.value ? searchTxt.value.trim() : undefined,
      output: output.value.trim() || undefined,
      verbose: verbose.value,
    })

    if (!data.success) {
      errorMsg.value = data.error ?? t('download.error_unexpected')
      return
    }

    if (verbose.value && data.job_id) {
      streamLogs(data.job_id)
    } else {
      successMsg.value = data.message ?? t('download.done')
    }
  } catch (err: unknown) {
    errorMsg.value = err instanceof Error ? err.message : t('download.error_unexpected')
  } finally {
    submitting.value = false
  }
}

/**
 * Open an SSE connection to stream logs for a running job.
 *
 * @param jobId - Hex job ID returned by POST /api/download.
 */
function streamLogs(jobId: string): void {
  const session = reactive<LogSession>({ jobId, lines: [], done: false, success: null, hidden: false })
  sessions.value.unshift(session)

  function scrollToBottom(): void {
    nextTick(() => {
      const el = terminalRefs.get(jobId)
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  const es = new EventSource(`/api/download/logs/${jobId}`)

  es.onmessage = (ev) => {
    session.lines.push(ev.data)
    scrollToBottom()
  }

  es.addEventListener('done', (ev: MessageEvent) => {
    try {
      const final = JSON.parse(ev.data) as JobDoneEvent
      session.done = true
      session.success = final.success
      if (final.success) {
        session.lines.push(`✓ ${t('download.done')} — ${final.message}`)
      } else {
        session.lines.push(`✗ ${t('download.failed')} — ${final.error || t('download.error_unexpected')}`)
      }
    } catch {
      session.lines.push(t('download.parse_error'))
    }
    scrollToBottom()
    es.close()
  })

  es.onerror = () => {
    if (!session.done) {
      session.lines.push(t('download.stream_disconnected'))
      session.done = true
    }
    es.close()
  }
}
</script>

<template>
  <div class="container py-5">
    <div class="row justify-content-center">
      <div class="col-lg-8">

        <!-- Download card -->
        <div class="card border-0 shadow-sm">
          <div class="card-header bg-primary text-white py-3">
            <h4 class="mb-0 fw-bold">
              <i class="bi bi-cloud-arrow-down me-2"></i>{{ t('download.title') }}
            </h4>
          </div>
          <div class="card-body p-4">

            <!-- Error / success alerts -->
            <div v-if="errorMsg" class="alert alert-danger py-2" role="alert">
              <i class="bi bi-exclamation-triangle-fill me-2"></i>{{ errorMsg }}
            </div>
            <div v-if="successMsg" class="alert alert-success py-2" role="alert">
              <i class="bi bi-check-circle-fill me-2"></i>{{ successMsg }}
            </div>

            <form @submit.prevent="handleSubmit" novalidate>
              <div class="row g-3">

                <!-- Source -->
                <div class="col-md-4">
                  <label for="source" class="form-label fw-semibold">{{ t('download.source_type') }}</label>
                  <select id="source" v-model="source" class="form-select">
                    <option value="single">{{ t('download.single_url') }}</option>
                    <option value="playlist">{{ t('download.playlist_url') }}</option>
                    <option value="search_txt">{{ t('download.search_text') }}</option>
                  </select>
                </div>

                <!-- Format -->
                <div class="col-md-4">
                  <label for="format" class="form-label fw-semibold">{{ t('download.format') }}</label>
                  <select id="format" v-model="format" class="form-select">
                    <option v-for="f in formats" :key="f" :value="f">{{ f.toUpperCase() }}</option>
                  </select>
                </div>

                <!-- Bitrate -->
                <div class="col-md-4">
                  <label for="bitrate" class="form-label fw-semibold">{{ t('download.bitrate') }}</label>
                  <select id="bitrate" v-model="bitrate" class="form-select">
                    <option v-for="b in bitrates" :key="b" :value="b">{{ b }}</option>
                  </select>
                </div>

                <!-- URL input -->
                <div v-if="!isSearchMode" class="col-12">
                  <label for="url" class="form-label fw-semibold">{{ t('download.url') }}</label>
                  <input
                    id="url"
                    v-model="url"
                    type="url"
                    class="form-control"
                    placeholder="https://www.youtube.com/watch?v=..."
                  />
                </div>

                <!-- Search textarea -->
                <div v-else class="col-12">
                  <label for="searchTxt" class="form-label fw-semibold">{{ t('download.search_queries') }}</label>
                  <textarea
                    id="searchTxt"
                    v-model="searchTxt"
                    class="form-control font-monospace"
                    rows="4"
                    :placeholder="t('download.placeholder_search')"
                  ></textarea>
                </div>

                <!-- Output folder -->
                <div class="col-12">
                  <label for="output" class="form-label fw-semibold">
                    {{ t('download.output_folder') }} <span class="text-muted fw-normal">({{ t('download.optional') }})</span>
                  </label>
                  <input
                    id="output"
                    v-model="output"
                    type="text"
                    class="form-control"
                    placeholder="e.g. Quena (saved to media/Quena)"
                  />
                </div>

                <!-- Verbose -->
                <div class="col-12">
                  <div class="form-check">
                    <input id="verbose" v-model="verbose" type="checkbox" class="form-check-input" />
                    <label for="verbose" class="form-check-label">
                      {{ t('download.verbose_label') }}
                    </label>
                  </div>
                </div>

                <!-- Submit -->
                <div class="col-12 mt-2">
                  <button type="submit" class="btn btn-primary w-100 py-2 fw-semibold" :disabled="submitting">
                    <span v-if="submitting" class="spinner-border spinner-border-sm me-2" role="status"></span>
                    {{ submitting ? t('download.submitting') : t('download.submit') }}
                  </button>
                </div>

              </div>
            </form>
          </div>
        </div>

        <!-- Log sessions -->
        <div v-if="sessions.length" class="mt-4">
          <div v-for="s in sessions" :key="s.jobId" class="mb-3">
            <div v-if="!s.hidden" class="card border-0 shadow-sm">
              <div class="card-header d-flex justify-content-between align-items-center py-2">
                <div class="d-flex align-items-center gap-2">
                  <span
                    class="badge"
                    :class="s.done ? (s.success ? 'bg-success' : 'bg-danger') : 'bg-warning text-dark'"
                  >
                    {{ s.done ? (s.success ? t('download.done') : t('download.failed')) : t('download.running') }}
                  </span>
                  <code class="small text-muted">{{ s.jobId }}</code>
                </div>
                <button type="button" class="btn-close" @click="s.hidden = true"></button>
              </div>
              <div class="card-body p-0">
                <pre
                  class="log-terminal m-0 p-3"
                  :ref="(el) => setTermRef(s.jobId, el as Element | null)"
                >{{ s.lines.join('\n') || ' ' }}</pre>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>
