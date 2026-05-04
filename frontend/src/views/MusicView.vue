<script setup lang="ts">
/**
 * MusicView.vue - AI Composer: generate full songs with ACE-Step 1.5.
 *
 * Submits a generation request to POST /api/music/generate, then opens
 * an SSE stream identical to the one used by DownloadView.  When the job
 * finishes, an inline audio player appears using the existing media stream
 * endpoint so no extra API routes are needed.
 */

import { ref, reactive, nextTick, onBeforeUnmount } from 'vue'
import { musicApi, mediaApi } from '@/services/api'
import { useI18n } from 'vue-i18n'
import type { MusicJobDoneEvent } from '@/services/types'

const { t } = useI18n()

// ── Form state ────────────────────────────────────────────────────────────────

const prompt = ref('')
const lyrics = ref('')
const duration = ref(60)
const showAdvanced = ref(false)
const inferSteps = ref(60)
const guidanceScale = ref(15.0)
const title = ref('')

const submitting = ref(false)
const errorMsg = ref('')

// ── Log sessions ──────────────────────────────────────────────────────────────

interface MusicSession {
  jobId: string
  lines: string[]
  done: boolean
  success: boolean | null
  hidden: boolean
  audioRelPath: string
}

const sessions = ref<MusicSession[]>([])
const activeStreams = new Map<string, EventSource>()

onBeforeUnmount(() => {
  activeStreams.forEach((es) => es.close())
  activeStreams.clear()
})

const terminalRefs = new Map<string, HTMLPreElement>()
function setTermRef(jobId: string, el: Element | null): void {
  if (el) terminalRefs.set(jobId, el as HTMLPreElement)
  else terminalRefs.delete(jobId)
}

// ── Submit ────────────────────────────────────────────────────────────────────

async function handleSubmit(): Promise<void> {
  errorMsg.value = ''
  if (!prompt.value.trim()) {
    errorMsg.value = t('music.error_no_prompt')
    return
  }

  submitting.value = true
  try {
    const { data } = await musicApi.generate({
      prompt: prompt.value.trim(),
      lyrics: lyrics.value.trim() || undefined,
      duration: duration.value,
      infer_steps: inferSteps.value,
      guidance_scale: guidanceScale.value,
      title: title.value.trim() || undefined,
    })

    if (!data.success) {
      errorMsg.value = data.error ?? t('music.error_unexpected')
      return
    }

    streamLogs(data.job_id)
  } catch (err: unknown) {
    errorMsg.value = err instanceof Error ? err.message : t('music.error_unexpected')
  } finally {
    submitting.value = false
  }
}

/**
 * Open an SSE connection for the given job ID.
 *
 * @param jobId - Hex job ID returned by POST /api/music/generate.
 */
function streamLogs(jobId: string): void {
  const session = reactive<MusicSession>({
    jobId,
    lines: [],
    done: false,
    success: null,
    hidden: false,
    audioRelPath: '',
  })
  sessions.value.unshift(session)

  function scrollToBottom(): void {
    nextTick(() => {
      const el = terminalRefs.get(jobId)
      if (el) el.scrollTop = el.scrollHeight
    })
  }

  const es = new EventSource(`/api/music/jobs/${jobId}/stream`)
  activeStreams.set(jobId, es)

  es.onmessage = (ev) => {
    session.lines.push(ev.data)
    scrollToBottom()
  }

  es.addEventListener('done', (ev: MessageEvent) => {
    try {
      const final = JSON.parse(ev.data) as MusicJobDoneEvent
      session.done = true
      session.success = final.success
      if (final.success && final.rel_path) {
        session.audioRelPath = final.rel_path
        session.lines.push(`✓ ${t('music.done')} — ${final.rel_path}`)
      } else {
        session.lines.push(`✗ ${t('music.failed')} — ${final.error || t('music.error_unexpected')}`)
      }
    } catch {
      session.lines.push(t('music.parse_error'))
    }
    scrollToBottom()
    es.close()
    activeStreams.delete(jobId)
  })

  es.onerror = () => {
    if (!session.done) {
      session.lines.push(t('music.stream_disconnected'))
      session.done = true
    }
    es.close()
    activeStreams.delete(jobId)
  }
}
</script>

<template>
  <div class="container py-5">
    <div class="row justify-content-center">
      <div class="col-lg-8">

        <!-- Header -->
        <div class="mb-4">
          <h2 class="fw-bold mb-1">
            <i class="bi bi-stars me-2 text-warning"></i>{{ t('music.title') }}
          </h2>
          <p class="text-muted mb-0">{{ t('music.subtitle') }}</p>
        </div>

        <!-- CPU warning -->
        <div class="alert alert-warning d-flex align-items-start gap-2 py-2 mb-4" role="alert">
          <i class="bi bi-hourglass-split flex-shrink-0 mt-1"></i>
          <span class="small">{{ t('music.cpu_warning') }}</span>
        </div>

        <!-- Generation card -->
        <div class="card border-0 shadow-sm">
          <div class="card-header bg-warning bg-opacity-10 border-bottom py-3">
            <h5 class="mb-0 fw-bold">
              <i class="bi bi-music-note-beamed me-2 text-warning"></i>{{ t('music.form_title') }}
            </h5>
          </div>
          <div class="card-body p-4">

            <div v-if="errorMsg" class="alert alert-danger py-2" role="alert">
              <i class="bi bi-exclamation-triangle-fill me-2"></i>{{ errorMsg }}
            </div>

            <form @submit.prevent="handleSubmit" novalidate>
              <div class="row g-3">

                <!-- Prompt -->
                <div class="col-12">
                  <label for="music-prompt" class="form-label fw-semibold">
                    {{ t('music.prompt_label') }}
                    <span class="text-danger ms-1">*</span>
                  </label>
                  <textarea
                    id="music-prompt"
                    v-model="prompt"
                    class="form-control"
                    rows="2"
                    :placeholder="t('music.prompt_placeholder')"
                  ></textarea>
                  <div class="form-text">{{ t('music.prompt_hint') }}</div>
                </div>

                <!-- Lyrics -->
                <div class="col-12">
                  <label for="music-lyrics" class="form-label fw-semibold">
                    {{ t('music.lyrics_label') }}
                    <span class="text-muted fw-normal ms-1">({{ t('music.optional') }})</span>
                  </label>
                  <textarea
                    id="music-lyrics"
                    v-model="lyrics"
                    class="form-control font-monospace"
                    rows="5"
                    :placeholder="t('music.lyrics_placeholder')"
                  ></textarea>
                  <div class="form-text">{{ t('music.lyrics_hint') }}</div>
                </div>

                <!-- Duration slider -->
                <div class="col-12">
                  <label for="music-duration" class="form-label fw-semibold">
                    {{ t('music.duration_label') }}
                    <span class="badge bg-secondary ms-2">{{ duration }}s</span>
                  </label>
                  <!-- Preset buttons -->
                  <div class="d-flex gap-2 mb-2 flex-wrap">
                    <button
                      v-for="preset in [30, 60, 90, 120, 180, 240]"
                      :key="preset"
                      type="button"
                      class="btn btn-sm"
                      :class="duration === preset ? 'btn-warning' : 'btn-outline-secondary'"
                      @click="duration = preset"
                    >{{ preset }}s</button>
                  </div>
                  <input
                    id="music-duration"
                    v-model.number="duration"
                    type="range"
                    class="form-range"
                    min="10"
                    max="240"
                    step="5"
                  />
                  <div class="d-flex justify-content-between">
                    <span class="form-text">10s</span>
                    <span class="form-text">240s</span>
                  </div>
                </div>

                <!-- Title (optional) -->
                <div class="col-12">
                  <label for="music-title" class="form-label fw-semibold">
                    {{ t('music.title_label') }}
                    <span class="text-muted fw-normal ms-1">({{ t('music.optional') }})</span>
                  </label>
                  <input
                    id="music-title"
                    v-model="title"
                    type="text"
                    class="form-control"
                    :placeholder="t('music.title_placeholder')"
                  />
                </div>

                <!-- Advanced options -->
                <div class="col-12">
                  <button
                    type="button"
                    class="btn btn-link text-decoration-none p-0 small"
                    @click="showAdvanced = !showAdvanced"
                  >
                    <i class="bi me-1" :class="showAdvanced ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
                    {{ t('music.advanced_toggle') }}
                  </button>
                </div>

                <template v-if="showAdvanced">
                  <!-- Infer steps -->
                  <div class="col-md-6">
                    <label for="music-steps" class="form-label fw-semibold">
                      {{ t('music.infer_steps_label') }}
                      <span class="badge bg-secondary ms-2">{{ inferSteps }}</span>
                    </label>
                    <input
                      id="music-steps"
                      v-model.number="inferSteps"
                      type="range"
                      class="form-range"
                      min="20"
                      max="150"
                      step="5"
                    />
                    <div class="form-text">{{ t('music.infer_steps_hint') }}</div>
                  </div>

                  <!-- Guidance scale -->
                  <div class="col-md-6">
                    <label for="music-guidance" class="form-label fw-semibold">
                      {{ t('music.guidance_label') }}
                      <span class="badge bg-secondary ms-2">{{ guidanceScale }}</span>
                    </label>
                    <input
                      id="music-guidance"
                      v-model.number="guidanceScale"
                      type="range"
                      class="form-range"
                      min="1"
                      max="20"
                      step="0.5"
                    />
                    <div class="form-text">{{ t('music.guidance_hint') }}</div>
                  </div>
                </template>

                <!-- Submit -->
                <div class="col-12 mt-2">
                  <button
                    type="submit"
                    class="btn btn-warning w-100 py-2 fw-semibold"
                    :disabled="submitting"
                  >
                    <span v-if="submitting" class="spinner-border spinner-border-sm me-2" role="status"></span>
                    <i v-else class="bi bi-stars me-2"></i>
                    {{ submitting ? t('music.generating') : t('music.generate_btn') }}
                  </button>
                </div>

              </div>
            </form>
          </div>
        </div>

        <!-- Generation sessions -->
        <div v-if="sessions.length" class="mt-4">
          <div v-for="s in sessions" :key="s.jobId" class="mb-4">
            <div v-if="!s.hidden" class="card border-0 shadow-sm">

              <!-- Session header -->
              <div class="card-header d-flex justify-content-between align-items-center py-2">
                <div class="d-flex align-items-center gap-2">
                  <span
                    class="badge"
                    :class="s.done ? (s.success ? 'bg-success' : 'bg-danger') : 'bg-warning text-dark'"
                  >
                    <span v-if="!s.done">
                      <span class="spinner-border spinner-border-sm me-1" role="status" style="width:0.65rem;height:0.65rem"></span>
                      {{ t('music.running') }}
                    </span>
                    <span v-else>{{ s.success ? t('music.done') : t('music.failed') }}</span>
                  </span>
                  <code class="small text-muted">{{ s.jobId.slice(0, 12) }}</code>
                </div>
                <button type="button" class="btn-close" @click="s.hidden = true"></button>
              </div>

              <!-- Log terminal -->
              <div class="card-body p-0">
                <pre
                  class="log-terminal m-0 p-3"
                  :ref="(el) => setTermRef(s.jobId, el as Element | null)"
                >{{ s.lines.join('\n') || ' ' }}</pre>
              </div>

              <!-- Audio player (shown on success) -->
              <div v-if="s.done && s.success && s.audioRelPath" class="card-footer bg-light p-3">
                <p class="small fw-semibold mb-2">
                  <i class="bi bi-music-note me-1 text-success"></i>{{ t('music.output_label') }}
                </p>
                <audio
                  :src="mediaApi.streamUrl(s.audioRelPath)"
                  controls
                  class="music-player-audio w-100 mb-2"
                ></audio>
                <div class="d-flex gap-2">
                  <a
                    :href="mediaApi.downloadUrl(s.audioRelPath)"
                    class="btn btn-sm btn-outline-secondary"
                  >
                    <i class="bi bi-download me-1"></i>{{ t('music.download_btn') }}
                  </a>
                  <RouterLink
                    to="/media/ai_composed"
                    class="btn btn-sm btn-outline-primary"
                  >
                    <i class="bi bi-folder2-open me-1"></i>{{ t('music.view_in_library') }}
                  </RouterLink>
                </div>
              </div>

            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>
