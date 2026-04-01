<script setup lang="ts">
/**
 * DeviceBanner.vue - Device detection banner for Stem Extraction pages.
 *
 * Shown at the top of every stem extraction page. On mount it calls
 * GET /api/stem/health and updates the label from "detecting…" to the
 * actual device name ("CPU" or "CUDA").
 */

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { stemApi } from '@/services/api'

const { t } = useI18n()
const device = ref<string | null>(null)
const error = ref(false)

onMounted(async () => {
  try {
    const { data } = await stemApi.health()
    device.value = data.device?.toUpperCase() ?? 'UNKNOWN'
  } catch {
    error.value = true
    device.value = 'unavailable'
  }
})
</script>

<template>
  <div
    class="alert d-flex align-items-center gap-2 py-2 mb-3"
    :class="error ? 'alert-warning' : 'alert-secondary'"
    role="status"
  >
    <i class="bi bi-cpu fs-5"></i>
    <span v-if="device === null" class="text-muted fst-italic">
      {{ t('stem.device_detecting') }}
    </span>
    <span v-else>
      {{ t('stem.device_label') }} <strong>{{ device }}</strong>
    </span>
    <span v-if="device === 'CPU'" class="ms-2 text-muted small">
      {{ t('stem.device_cpu_warning') }}
    </span>
  </div>
</template>
