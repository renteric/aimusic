<script setup lang="ts">
/**
 * StorageDashboardView.vue - Media storage usage dashboard.
 *
 * Displays total size, file count, and breakdowns by format and folder
 * using Bootstrap progress bars (no external charting library needed).
 */

import { fetchStorageStats } from '@/services/api'
import type { StorageStats, StorageRow } from '@/services/types'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const stats = ref<StorageStats | null>(null)
const loading = ref(true)
const error = ref('')

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`
  return `${(bytes / 1073741824).toFixed(2)} GB`
}

function pct(bytes: number): number {
  if (!stats.value || stats.value.total_bytes === 0) return 0
  return Math.max(1, Math.round((bytes / stats.value.total_bytes) * 100))
}

// Colour palette for format bars.
const FORMAT_COLORS: Record<string, string> = {
  '.mp3':     'bg-primary',
  '.flac':    'bg-success',
  '.wav':     'bg-info',
  '.ogg':     'bg-warning',
  '.opus':    'bg-secondary',
  '.m4a':     'bg-danger',
  '.md':      'bg-light',
  '.json':    'bg-dark',
  '.mid':     'bg-primary',
  '.musicxml':'bg-success',
  '.csv':     'bg-warning',
}

function barColor(ext: string): string {
  return FORMAT_COLORS[ext] ?? 'bg-secondary'
}

// Sort-able column for folders
const folderSort = ref<'bytes' | 'count'>('bytes')
const sortedFolders = computed((): StorageRow[] => {
  if (!stats.value) return []
  return [...stats.value.by_folder].sort((a, b) => b[folderSort.value] - a[folderSort.value])
})

onMounted(async () => {
  try {
    const { data } = await fetchStorageStats()
    stats.value = data
  } catch {
    error.value = t('storage.error_load')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="container py-4">

    <!-- Header -->
    <div class="mb-4">
      <h2 class="mb-0 fw-bold">
        <i class="bi bi-pie-chart me-2 text-primary"></i>{{ t('storage.title') }}
      </h2>
      <p class="text-muted small mb-0">{{ t('storage.subtitle') }}</p>
    </div>

    <!-- Error -->
    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <!-- Loading -->
    <div v-else-if="loading" class="text-center py-5 text-muted">
      <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
    </div>

    <template v-else-if="stats">

      <!-- Summary cards -->
      <div class="row g-3 mb-4">
        <div class="col-md-4">
          <div class="card border-0 shadow-sm text-center h-100">
            <div class="card-body py-4">
              <div class="display-6 fw-bold text-primary">{{ humanSize(stats.total_bytes) }}</div>
              <div class="text-muted small mt-1">{{ t('storage.total_size') }}</div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card border-0 shadow-sm text-center h-100">
            <div class="card-body py-4">
              <div class="display-6 fw-bold text-success">{{ stats.total_files.toLocaleString() }}</div>
              <div class="text-muted small mt-1">{{ t('storage.total_files') }}</div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card border-0 shadow-sm text-center h-100">
            <div class="card-body py-4">
              <div class="display-6 fw-bold text-info">{{ stats.by_folder.length }}</div>
              <div class="text-muted small mt-1">{{ t('storage.total_folders') }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="row g-4">

        <!-- By format -->
        <div class="col-lg-6">
          <div class="card border-0 shadow-sm h-100">
            <div class="card-header py-2">
              <strong class="small"><i class="bi bi-file-earmark me-1"></i>{{ t('storage.by_format') }}</strong>
            </div>
            <div class="card-body">
              <div v-for="row in stats.by_format" :key="row.ext ?? ''" class="mb-3">
                <div class="d-flex justify-content-between align-items-center mb-1">
                  <span class="fw-semibold small font-monospace">{{ row.ext }}</span>
                  <span class="text-muted small">
                    {{ row.count }} {{ t('storage.files') }} · {{ humanSize(row.bytes) }}
                  </span>
                </div>
                <div class="progress" style="height: 10px;">
                  <div
                    class="progress-bar"
                    :class="barColor(row.ext ?? '')"
                    :style="{ width: pct(row.bytes) + '%' }"
                    :title="pct(row.bytes) + '%'"
                  ></div>
                </div>
              </div>
              <div v-if="stats.by_format.length === 0" class="text-muted text-center py-3 small">
                {{ t('storage.no_data') }}
              </div>
            </div>
          </div>
        </div>

        <!-- By folder -->
        <div class="col-lg-6">
          <div class="card border-0 shadow-sm h-100">
            <div class="card-header d-flex align-items-center justify-content-between py-2">
              <strong class="small"><i class="bi bi-folder me-1"></i>{{ t('storage.by_folder') }}</strong>
              <div class="btn-group btn-group-sm">
                <button
                  class="btn btn-outline-secondary"
                  :class="{ active: folderSort === 'bytes' }"
                  @click="folderSort = 'bytes'"
                >{{ t('storage.sort_size') }}</button>
                <button
                  class="btn btn-outline-secondary"
                  :class="{ active: folderSort === 'count' }"
                  @click="folderSort = 'count'"
                >{{ t('storage.sort_files') }}</button>
              </div>
            </div>
            <div class="card-body p-0">
              <table class="table table-hover align-middle mb-0 small">
                <thead class="table-light">
                  <tr>
                    <th class="ps-3">{{ t('storage.folder') }}</th>
                    <th class="text-end">{{ t('storage.files') }}</th>
                    <th class="text-end pe-3">{{ t('storage.size') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in sortedFolders" :key="row.folder ?? ''">
                    <td class="ps-3">
                      <i class="bi bi-folder-fill text-warning me-1"></i>
                      <code>{{ row.folder }}</code>
                    </td>
                    <td class="text-end text-muted">{{ row.count }}</td>
                    <td class="text-end pe-3 fw-semibold">{{ humanSize(row.bytes) }}</td>
                  </tr>
                  <tr v-if="sortedFolders.length === 0">
                    <td colspan="3" class="text-center text-muted py-3">{{ t('storage.no_data') }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

      </div>
    </template>

  </div>
</template>
