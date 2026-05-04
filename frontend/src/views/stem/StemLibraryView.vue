<script setup lang="ts">
/**
 * StemLibraryView.vue - Stem Extraction Library page for AI-Music.
 *
 * Browses and manages extracted stem output folders stored in media/stems/.
 * Shows all output folders with their file counts, lets users expand a folder
 * to preview and download individual stems, and delete folders they no longer need.
 */

import DeviceBanner from '@/components/DeviceBanner.vue'
import { stemApi } from '@/services/api'
import type { StemFile, StemFolder } from '@/services/types'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

// ── State ─────────────────────────────────────────────────────────────────────

const folders = ref<StemFolder[]>([])
const openFolder = ref<string | null>(null)
const folderFiles = ref<Record<string, StemFile[]>>({})
const loadingFolder = ref<string | null>(null)

const isLoading = ref(true)
const loadError = ref('')

const deletingFolder = ref<string | null>(null)
const deleteError = ref('')

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(loadLibrary)

async function loadLibrary() {
  isLoading.value = true
  loadError.value = ''
  try {
    const { data } = await stemApi.library()
    folders.value = data.folders
  } catch {
    loadError.value = 'Failed to load stem library.'
  } finally {
    isLoading.value = false
  }
}

// ── Folder expand / collapse ──────────────────────────────────────────────────

async function toggleFolder(folder: string) {
  if (openFolder.value === folder) {
    openFolder.value = null
    return
  }
  openFolder.value = folder
  if (folderFiles.value[folder]) return

  loadingFolder.value = folder
  try {
    const { data } = await stemApi.libraryFolder(folder)
    folderFiles.value[folder] = data.files
  } catch {
    folderFiles.value[folder] = []
  } finally {
    loadingFolder.value = null
  }
}

// ── Delete folder ─────────────────────────────────────────────────────────────

async function deleteFolder(folder: string) {
  if (!confirm(`Delete all stems in "${folder}"? This cannot be undone.`)) return
  deletingFolder.value = folder
  deleteError.value = ''
  try {
    await stemApi.deleteFolder(folder)
    folders.value = folders.value.filter((f) => f.name !== folder)
    delete folderFiles.value[folder]
    if (openFolder.value === folder) openFolder.value = null
  } catch (err: any) {
    deleteError.value = err.response?.data?.detail ?? `Failed to delete ${folder}.`
  } finally {
    deletingFolder.value = null
  }
}

// ── Download ───────────────────────────────────────────────────────────────────

function streamUrl(relPath: string): string {
  return `/api/media/stream/${relPath}`
}

function downloadUrl(relPath: string): string {
  return `/api/media/download/${relPath}`
}
</script>

<template>
  <div class="container py-4">
    <h2 class="mb-1 fw-bold"><span class="me-2">📋</span>{{ t('stem.library_title') }}</h2>
    <p class="text-muted mb-3">{{ t('stem.library_subtitle') }}</p>

    <!-- Device banner -->
    <DeviceBanner />

    <!-- Load error -->
    <div v-if="loadError" class="alert alert-danger" role="alert">{{ loadError }}</div>

    <!-- Delete error -->
    <div v-if="deleteError" class="alert alert-danger alert-dismissible" role="alert">
      {{ deleteError }}
      <button type="button" class="btn-close" @click="deleteError = ''"></button>
    </div>

    <!-- Loading spinner -->
    <div v-if="isLoading" class="text-center py-5 text-muted">
      <div class="spinner-border spinner-border-sm me-2"></div>
      {{ t('common.loading') }}
    </div>

    <!-- Empty state -->
    <div v-else-if="folders.length === 0" class="text-center py-5 text-muted">
      <div class="fs-1 mb-3">🎵</div>
      <div class="fw-semibold">{{ t('stem.library_empty') }}</div>
      <div class="small mt-1">{{ t('stem.library_empty_hint') }}</div>
    </div>

    <!-- Folder list -->
    <div v-else class="list-group">
      <div
        v-for="folder in folders"
        :key="folder.name"
        class="list-group-item list-group-item-action p-0 overflow-hidden"
      >
        <!-- Folder header row -->
        <div class="d-flex align-items-center gap-3 px-3 py-2">
          <button
            class="btn btn-sm btn-link text-decoration-none p-0 flex-shrink-0"
            :aria-label="openFolder === folder.name ? 'Collapse' : 'Expand'"
            @click="toggleFolder(folder.name)"
          >
            <i
              class="bi"
              :class="openFolder === folder.name ? 'bi-chevron-down' : 'bi-chevron-right'"
            ></i>
          </button>

          <RouterLink
            :to="`/stem/library/${encodeURIComponent(folder.name)}`"
            class="flex-grow-1 text-decoration-none text-body"
          >
            <div class="fw-semibold">{{ folder.display_name }}</div>
            <div class="text-muted small">{{ folder.audio_count }} stem{{ folder.audio_count !== 1 ? 's' : '' }}</div>
          </RouterLink>

          <button
            class="btn btn-sm btn-outline-danger flex-shrink-0"
            :disabled="deletingFolder === folder.name"
            @click.stop="deleteFolder(folder.name)"
          >
            <span v-if="deletingFolder === folder.name" class="spinner-border spinner-border-sm"></span>
            <span v-else><i class="bi bi-trash"></i></span>
          </button>
        </div>

        <!-- Expanded file list -->
        <div v-if="openFolder === folder.name" class="border-top bg-body-tertiary">
          <div v-if="loadingFolder === folder.name" class="text-center text-muted py-3 small">
            <div class="spinner-border spinner-border-sm me-1"></div>
            Loading files…
          </div>

          <div v-else-if="folderFiles[folder.name]?.length === 0" class="text-center text-muted py-3 small">
            No files found in this folder.
          </div>

          <div v-else class="list-group list-group-flush">
            <div
              v-for="file in folderFiles[folder.name]"
              :key="file.filename"
              class="list-group-item d-flex align-items-center gap-3 ps-4"
            >
              <div class="fs-5 flex-shrink-0">🎵</div>
              <div class="flex-grow-1">
                <div class="fw-semibold small">{{ file.stem_name || file.filename }}</div>
                <div class="text-muted stem-filename">
                  {{ file.filename }} · {{ file.size_mb.toFixed(1) }} MB
                </div>
              </div>
              <audio
                :src="streamUrl(file.rel_path)"
                controls
                class="flex-shrink-0 stem-mini-player"
              ></audio>
              <a
                :href="downloadUrl(file.rel_path)"
                class="btn btn-sm btn-outline-secondary flex-shrink-0"
                :download="file.filename"
              >⬇</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Refresh button -->
    <div class="mt-3">
      <button class="btn btn-outline-secondary btn-sm" :disabled="isLoading" @click="loadLibrary">
        <i class="bi bi-arrow-clockwise me-1"></i>Refresh
      </button>
    </div>
  </div>
</template>
