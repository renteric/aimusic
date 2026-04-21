<script setup lang="ts">
/**
 * StemPlayerView.vue - Stem player page for a single output folder.
 *
 * Key design decisions:
 * - audioEls is a plain object, never reactive — Vue must never Proxy HTMLAudioElement.
 * - audio.muted = true/false is used for mute, not volume = 0 (more reliable).
 * - preload="none" avoids loading all stems on page open.
 * - A single requestAnimationFrame loop drives the timeline (no per-stem timeupdate listeners).
 * - Sync: all stems seek to stem[0].currentTime after play() resolves.
 */

import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { stemApi } from '@/services/api'
import type { StemFile } from '@/services/types'

const BOUNCE_BITRATES = ['128k', '192k', '256k', '320k'] as const

const BOUNCE_FORMATS = [
  { value: 'mp3',  label: 'MP3',  lossy: true },
  { value: 'flac', label: 'FLAC — lossless', lossy: false },
  { value: 'wav',  label: 'WAV — lossless', lossy: false },
  { value: 'ogg',  label: 'OGG Vorbis', lossy: true },
  { value: 'opus', label: 'Opus', lossy: true },
] as const

// ── Route ─────────────────────────────────────────────────────────────────────

const route = useRoute()
const router = useRouter()
const folderName = computed(() => route.params.folder as string)

// ── Data ───────────────────────────────────────────────────────────────────────

const files = ref<StemFile[]>([])
const loadError = ref('')
const isLoading = ref(true)

// ── Audio elements — PLAIN object, never let Vue wrap these in a Proxy ─────────

const audioEls: Record<string, HTMLAudioElement> = {}

// ── Per-stem reactive UI state ─────────────────────────────────────────────────

interface StemState {
  volume: number      // 0..1 slider value
  muted: boolean
  playing: boolean
  savedVolume: number // volume before mute
}

const stemState = reactive<Record<string, StemState>>({})

// ── Master ─────────────────────────────────────────────────────────────────────

const masterPlaying = ref(false)
const loadingAudio = ref(false)

// ── Timeline (driven by RAF, not per-element listeners) ───────────────────────

const currentTime = ref(0)
const duration = ref(0)
const seeking = ref(false)

const timelinePercent = computed(() =>
  duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0,
)

let rafId: number | null = null

function startRaf() {
  if (rafId !== null) return
  function tick() {
    const first = firstAudio()
    if (first && !isNaN(first.duration)) {
      if (!seeking.value) currentTime.value = first.currentTime
      duration.value = first.duration
    }
    rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
}

function stopRaf() {
  if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
}

function firstAudio(): HTMLAudioElement | undefined {
  return Object.values(audioEls)[0]
}

// ── Pitch ──────────────────────────────────────────────────────────────────────

const keyShift = ref(0)

function applyPitch() {
  const rate = Math.pow(2, keyShift.value / 12)
  Object.values(audioEls).forEach((a) => { a.playbackRate = rate })
}

function shiftKey(delta: number) {
  keyShift.value = Math.max(-12, Math.min(12, keyShift.value + delta))
  applyPitch()
}

function resetKey() {
  keyShift.value = 0
  applyPitch()
}

// ── Lifecycle ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  try {
    const { data } = await stemApi.libraryFolder(folderName.value)
    files.value = data.files
    for (const f of data.files) {
      stemState[f.stem_name] = { volume: 0.8, muted: false, playing: false, savedVolume: 0.8 }
    }
  } catch {
    loadError.value = `Folder "${folderName.value}" not found or could not be loaded.`
  } finally {
    isLoading.value = false
  }
  startRaf()
})

onBeforeUnmount(() => {
  stopRaf()
  Object.values(audioEls).forEach((a) => { a.pause(); a.src = '' })
})

// ── Ref callback ───────────────────────────────────────────────────────────────

function registerAudio(el: Element | null, stemName: string) {
  if (!el) {
    delete audioEls[stemName]
    return
  }
  const audio = el as HTMLAudioElement
  audioEls[stemName] = audio

  const state = stemState[stemName]
  if (state) {
    audio.volume = state.volume
    audio.muted = state.muted
  }

  audio.addEventListener('ended', () => {
    if (stemState[stemName]) stemState[stemName].playing = false
    if (masterPlaying.value && !Object.values(stemState).some((s) => s.playing)) {
      masterPlaying.value = false
    }
  })
}

// ── Timeline seek ──────────────────────────────────────────────────────────────

function onSeek(e: Event) {
  const pct = parseFloat((e.target as HTMLInputElement).value)
  const target = (pct / 100) * duration.value
  Object.values(audioEls).forEach((a) => {
    if (!isNaN(a.duration)) a.currentTime = target
  })
  currentTime.value = target
}

// ── Master play / pause ────────────────────────────────────────────────────────

async function toggleMaster() {
  if (!masterPlaying.value) {
    // Reset all to start
    Object.values(audioEls).forEach((a) => { a.currentTime = 0 })
    currentTime.value = 0

    // Preload all stems that haven't been loaded yet.
    // With preload="none", firing play() on 9 elements at once hits the browser's
    // 6-connection-per-host limit (HTTP/1.1), so the last 3 never start.
    // Solution: trigger load() on all, wait for every element to reach
    // HAVE_FUTURE_DATA (readyState >= 3), then fire play() in one tight loop.
    const needsLoad = Object.values(audioEls).some((a) => a.readyState < 3)
    if (needsLoad) {
      loadingAudio.value = true
      await Promise.all(
        Object.values(audioEls).map((audio) => {
          if (audio.readyState >= 3) return Promise.resolve()
          return new Promise<void>((resolve) => {
            const done = () => {
              audio.removeEventListener('canplaythrough', done)
              audio.removeEventListener('error', done)
              resolve()
            }
            audio.addEventListener('canplaythrough', done, { once: true })
            audio.addEventListener('error', done, { once: true })
            // 8-second fallback in case canplaythrough never fires (e.g. for very large files)
            setTimeout(resolve, 8000)
            audio.preload = 'auto'
            audio.load()
          })
        }),
      )
      loadingAudio.value = false
    }

    // Fire all play() calls synchronously (no await between them) for tightest sync.
    // Awaiting Promise.all afterwards still catches rejections without introducing lag.
    const plays: Promise<void>[] = []
    for (const [name, audio] of Object.entries(audioEls)) {
      const p = audio.play()
      stemState[name].playing = true
      if (p) plays.push(p.catch(() => { stemState[name].playing = false }))
    }
    await Promise.all(plays)
    applyPitch()

    // Re-align all stems to the first one (compensate for any remaining start-up drift)
    const t = firstAudio()?.currentTime ?? 0
    if (t > 0) Object.values(audioEls).forEach((a) => { a.currentTime = t })

    masterPlaying.value = true
  } else {
    Object.entries(audioEls).forEach(([name, a]) => {
      a.pause()
      stemState[name].playing = false
    })
    masterPlaying.value = false
  }
}

// ── Per-stem play / pause ──────────────────────────────────────────────────────

async function toggleStem(stemName: string) {
  const audio = audioEls[stemName]
  const state = stemState[stemName]
  if (!audio || !state) return

  if (audio.paused) {
    if (!masterPlaying.value) {
      // Solo: pause all others
      Object.entries(audioEls).forEach(([name, a]) => {
        if (name !== stemName && !a.paused) {
          a.pause()
          stemState[name].playing = false
        }
      })
    }
    await audio.play().catch(() => null)
    applyPitch()
    state.playing = true
  } else {
    audio.pause()
    state.playing = false
    if (masterPlaying.value && !Object.values(stemState).some((s) => s.playing)) {
      masterPlaying.value = false
    }
  }
}

// ── Volume ─────────────────────────────────────────────────────────────────────

function onVolume(stemName: string, e: Event) {
  const vol = parseFloat((e.target as HTMLInputElement).value)
  const state = stemState[stemName]
  const audio = audioEls[stemName]
  if (!state || !audio) return
  state.volume = vol
  state.savedVolume = vol
  // Only apply if not muted
  if (!state.muted) audio.volume = vol
}

// ── Mute ───────────────────────────────────────────────────────────────────────

function toggleMute(stemName: string) {
  const state = stemState[stemName]
  const audio = audioEls[stemName]
  if (!state || !audio) return

  if (state.muted) {
    state.muted = false
    audio.muted = false          // native muted flag — most reliable
    audio.volume = state.savedVolume
    state.volume = state.savedVolume
  } else {
    state.savedVolume = state.volume
    state.muted = true
    audio.muted = true           // native muted flag — most reliable
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatTime(s: number): string {
  if (!s || isNaN(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function streamUrl(relPath: string): string {
  return `/api/media/stream/${relPath}`
}

function downloadUrl(relPath: string): string {
  return `/api/media/download/${relPath}`
}

const displayName = computed(() =>
  folderName.value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
)

// ── Bounce ─────────────────────────────────────────────────────────────────────

const bounceName = ref('')
const bounceFormat = ref('mp3')
const bounceBitrate = ref('320k')
const bouncing = ref(false)
const bounceResult = ref('')
const bounceError = ref('')

const bounceFormatLossy = computed(() =>
  BOUNCE_FORMATS.find((f) => f.value === bounceFormat.value)?.lossy ?? true,
)

async function handleBounce(): Promise<void> {
  bouncing.value = true
  bounceResult.value = ''
  bounceError.value = ''

  // Build volumes map: filename → current volume (0 if muted)
  const volumes: Record<string, number> = {}
  for (const file of files.value) {
    const state = stemState[file.stem_name]
    volumes[file.filename] = state?.muted ? 0 : (state?.volume ?? 0.8)
  }

  try {
    const { data } = await stemApi.bounce({
      folder: folderName.value,
      volumes,
      output_name: bounceName.value.trim() || undefined,
      format: bounceFormat.value,
      bitrate: bounceBitrate.value,
    })
    bounceResult.value = data.filename
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    bounceError.value = msg ?? 'Bounce failed.'
  } finally {
    bouncing.value = false
  }
}
</script>

<template>
  <div class="container py-4">

    <!-- Hidden audio elements — plain preload="none", loaded on first play -->
    <div aria-hidden="true" class="stem-audio-sink">
      <audio
        v-for="file in files"
        :key="file.stem_name"
        :ref="(el) => registerAudio(el as Element | null, file.stem_name)"
        preload="none"
      >
        <source :src="streamUrl(file.rel_path)" type="audio/mpeg" />
      </audio>
    </div>

    <!-- Header -->
    <div class="d-flex align-items-center gap-3 mb-4">
      <button class="btn btn-outline-secondary btn-sm" @click="router.push('/stem/library')">
        <i class="bi bi-arrow-left me-1"></i>Library
      </button>
      <div>
        <h2 class="mb-0 fw-bold">🎵 {{ displayName }}</h2>
        <div class="text-muted small">{{ files.length }} stem{{ files.length !== 1 ? 's' : '' }}</div>
      </div>
    </div>

    <!-- Load error -->
    <div v-if="loadError" class="alert alert-danger">{{ loadError }}</div>

    <!-- Loading -->
    <div v-else-if="isLoading" class="text-center text-muted py-5">
      <div class="spinner-border spinner-border-sm me-2"></div>Loading stems…
    </div>

    <!-- Empty -->
    <div v-else-if="files.length === 0" class="text-center text-muted py-5">
      No audio files found in this folder.
    </div>

    <template v-else>

      <!-- Master play button -->
      <div class="mb-3">
        <button
          class="btn btn-lg"
          :class="masterPlaying ? 'btn-warning' : 'btn-success'"
          :disabled="loadingAudio"
          @click="toggleMaster"
        >
          <span v-if="loadingAudio" class="spinner-border spinner-border-sm me-2" role="status"></span>
          <i v-else class="bi me-2" :class="masterPlaying ? 'bi-pause-fill' : 'bi-play-fill'"></i>
          {{ loadingAudio ? 'Loading stems…' : masterPlaying ? 'Pause All' : 'Play All Stems' }}
        </button>
      </div>

      <!-- Timeline -->
      <div class="card mb-3">
        <div class="card-body py-2">
          <div class="d-flex align-items-center gap-3">
            <span class="text-muted small font-monospace stem-time-display">
              {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
            </span>
            <input
              type="range"
              class="form-range flex-grow-1"
              min="0"
              max="100"
              step="0.1"
              :value="timelinePercent"
              @mousedown="seeking = true"
              @touchstart="seeking = true"
              @input="onSeek"
              @mouseup="seeking = false"
              @touchend="seeking = false"
            />
          </div>
        </div>
      </div>

      <!-- Key / pitch -->
      <div class="card mb-4">
        <div class="card-body py-2">
          <div class="d-flex align-items-center gap-3 flex-wrap">
            <span class="fw-semibold small">Song Key:</span>
            <button class="btn btn-sm btn-outline-secondary" @click="shiftKey(-1)">♭</button>
            <span class="font-monospace fw-bold stem-key-display">
              {{ keyShift > 0 ? '+' : '' }}{{ keyShift }} semitones
            </span>
            <button class="btn btn-sm btn-outline-secondary" @click="shiftKey(1)">♯</button>
            <input
              type="range"
              class="form-range stem-pitch-range"
              min="-12"
              max="12"
              step="1"
              :value="keyShift"
              @input="(e) => { keyShift = parseInt((e.target as HTMLInputElement).value); applyPitch() }"
            />
            <button class="btn btn-sm btn-outline-danger" @click="resetKey">Reset</button>
          </div>
        </div>
      </div>

      <!-- Stems table -->
      <div class="card">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-dark">
              <tr>
                <th>Stem</th>
                <th>Play</th>
                <th class="stem-vol-col">Volume</th>
                <th>Download</th>
                <th>Mute</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="file in files" :key="file.filename">

                <!-- Stem name -->
                <td>
                  <div class="d-flex align-items-center gap-2">
                    <span class="stem-dot bg-secondary"></span>
                    <div>
                      <div class="fw-semibold">{{ file.stem_name }}</div>
                      <div class="text-muted stem-filename">
                        {{ file.filename }} · {{ file.size_mb }} MB
                      </div>
                    </div>
                  </div>
                </td>

                <!-- Play -->
                <td>
                  <button
                    class="btn btn-sm"
                    :class="stemState[file.stem_name]?.playing ? 'btn-warning' : 'btn-outline-primary'"
                    @click="toggleStem(file.stem_name)"
                  >
                    <i class="bi"
                       :class="stemState[file.stem_name]?.playing ? 'bi-pause-fill' : 'bi-play-fill'"
                    ></i>
                  </button>
                </td>

                <!-- Volume -->
                <td>
                  <div class="d-flex align-items-center gap-2">
                    <input
                      type="range"
                      class="form-range stem-vol-range"
                      min="0"
                      max="1"
                      step="0.01"
                      :value="stemState[file.stem_name]?.volume ?? 0.8"
                      :disabled="stemState[file.stem_name]?.muted"
                      @input="onVolume(file.stem_name, $event)"
                    />
                    <span class="text-muted small stem-vol-label">
                      {{ stemState[file.stem_name]?.muted
                          ? '🔇'
                          : Math.round((stemState[file.stem_name]?.volume ?? 0.8) * 100) + '%' }}
                    </span>
                  </div>
                </td>

                <!-- Download -->
                <td>
                  <a
                    :href="downloadUrl(file.rel_path)"
                    class="btn btn-sm btn-outline-secondary"
                    :download="file.filename"
                  >
                    <i class="bi bi-download"></i>
                  </a>
                </td>

                <!-- Mute -->
                <td>
                  <button
                    class="btn btn-sm"
                    :class="stemState[file.stem_name]?.muted ? 'btn-danger' : 'btn-outline-secondary'"
                    :title="stemState[file.stem_name]?.muted ? 'Unmute' : 'Mute'"
                    @click="toggleMute(file.stem_name)"
                  >
                    <i class="bi"
                       :class="stemState[file.stem_name]?.muted ? 'bi-volume-mute-fill' : 'bi-volume-up-fill'"
                    ></i>
                  </button>
                </td>

              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Bounce / Export panel -->
      <div class="card mt-4">
        <div class="card-header py-2">
          <strong class="small">
            <i class="bi bi-file-earmark-music me-1 text-primary"></i>Bounce / Export Mix
          </strong>
        </div>
        <div class="card-body">
          <p class="text-muted small mb-3">
            Mix all stems at their current volume levels and export a new MP3. Muted stems are excluded.
          </p>
          <div class="row g-3 align-items-end">
            <div class="col-md-4">
              <label class="form-label small mb-1">Output filename (optional)</label>
              <input
                v-model="bounceName"
                type="text"
                class="form-control form-control-sm"
                :placeholder="`${folderName}_bounce`"
                :disabled="bouncing"
              />
            </div>
            <div class="col-md-2">
              <label class="form-label small mb-1">Format</label>
              <select v-model="bounceFormat" class="form-select form-select-sm" :disabled="bouncing">
                <option v-for="f in BOUNCE_FORMATS" :key="f.value" :value="f.value">{{ f.label }}</option>
              </select>
            </div>
            <div class="col-md-2">
              <label class="form-label small mb-1">Bitrate</label>
              <select
                v-model="bounceBitrate"
                class="form-select form-select-sm"
                :disabled="bouncing || !bounceFormatLossy"
                :title="bounceFormatLossy ? '' : 'Not applicable for lossless formats'"
              >
                <option v-for="b in BOUNCE_BITRATES" :key="b" :value="b">{{ b }}</option>
              </select>
            </div>
            <div class="col-md-4">
              <button
                class="btn btn-primary w-100"
                :disabled="bouncing"
                @click="handleBounce"
              >
                <span v-if="bouncing" class="spinner-border spinner-border-sm me-2"></span>
                <i v-else class="bi bi-arrow-down-circle me-2"></i>
                {{ bouncing ? 'Exporting…' : `Bounce to ${bounceFormat.toUpperCase()}` }}
              </button>
            </div>
          </div>

          <!-- Volume preview (active stems) -->
          <div class="mt-3 d-flex flex-wrap gap-2">
            <span
              v-for="file in files"
              :key="file.filename"
              class="badge"
              :class="stemState[file.stem_name]?.muted ? 'bg-secondary' : 'bg-primary'"
            >
              {{ file.stem_name }}
              {{ stemState[file.stem_name]?.muted
                ? '🔇'
                : Math.round((stemState[file.stem_name]?.volume ?? 0.8) * 100) + '%' }}
            </span>
          </div>

          <!-- Result -->
          <div v-if="bounceResult" class="alert alert-success mt-3 mb-0 py-2 small">
            <i class="bi bi-check-circle me-1"></i>
            Exported as <strong>{{ bounceResult }}</strong> — find it in
            <a href="/media" class="alert-link">Media Files</a>.
          </div>
          <div v-if="bounceError" class="alert alert-danger mt-3 mb-0 py-2 small">
            <i class="bi bi-exclamation-circle me-1"></i>{{ bounceError }}
          </div>
        </div>
      </div>

    </template>
  </div>
</template>
