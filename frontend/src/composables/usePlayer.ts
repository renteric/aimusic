/**
 * usePlayer.ts - Vue composable for the shared in-page audio player.
 *
 * One Audio instance is shared across the whole application (module-level
 * singleton). Only one track can play at a time; switching tracks stops the
 * previous one and resets its UI state via reactive refs.
 *
 * Usage:
 * ```ts
 * const { play, activeUrl, isPlaying, progress } = usePlayer()
 * play('/api/media/stream/folder/track.mp3')
 * ```
 */

import { ref, readonly } from 'vue'

// ── Module-level singleton ────────────────────────────────────────────────────

const audio = new Audio()
audio.preload = 'metadata'

const activeUrl = ref<string | null>(null)
const isPlaying = ref(false)
const progress = ref(0) // 0–100

audio.addEventListener('timeupdate', () => {
  if (audio.duration && isFinite(audio.duration)) {
    progress.value = Math.min(100, (audio.currentTime / audio.duration) * 100)
  }
})

audio.addEventListener('ended', () => {
  isPlaying.value = false
  progress.value = 0
})

audio.addEventListener('pause', () => {
  isPlaying.value = false
})

audio.addEventListener('play', () => {
  isPlaying.value = true
})

// ── Composable factory ────────────────────────────────────────────────────────

/**
 * Returns reactive player state and control functions.
 *
 * @returns Player state and actions.
 */
export function usePlayer() {
  /**
   * Play or toggle a track by its stream URL.
   *
   * - If the given URL is already active, toggles play/pause.
   * - Otherwise stops the current track and starts the new one.
   *
   * @param url - Full URL to the audio stream (e.g. `/api/media/stream/...`).
   */
  function play(url: string): void {
    if (activeUrl.value === url) {
      audio.paused ? audio.play().catch(() => {}) : audio.pause()
      return
    }

    audio.pause()
    activeUrl.value = url
    progress.value = 0
    audio.src = url
    audio.currentTime = 0
    audio.play().catch(() => {
      isPlaying.value = false
    })
  }

  /** Stop playback and clear active state. */
  function stop(): void {
    audio.pause()
    activeUrl.value = null
    progress.value = 0
  }

  return {
    /** URL of the currently active track, or null. */
    activeUrl: readonly(activeUrl),
    /** True when audio is playing. */
    isPlaying: readonly(isPlaying),
    /** Playback progress 0–100. */
    progress: readonly(progress),
    play,
    stop,
  }
}
