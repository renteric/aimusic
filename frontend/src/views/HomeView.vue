<script setup lang="ts">
/**
 * HomeView.vue - Landing page for AI-Powered-Music.
 *
 * Displays feature highlight cards and a prominent call-to-action button
 * linking to the Download page. Admin-only cards are filtered by role.
 */

import { useAuthStore } from '@/stores/auth'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const auth = useAuthStore()
const { t } = useI18n()

interface Feature {
  icon: string
  titleKey: string
  textKey: string
  adminOnly?: true
}

/** All feature highlights — admin-only cards are hidden for non-admin roles. */
const features: Feature[] = [
  { icon: 'bi-music-note-list',   titleKey: 'home.features.multiple_formats.title',  textKey: 'home.features.multiple_formats.text' },
  { icon: 'bi-collection-play',   titleKey: 'home.features.batch_download.title',     textKey: 'home.features.batch_download.text' },
  { icon: 'bi-speedometer2',      titleKey: 'home.features.real_time_logs.title',     textKey: 'home.features.real_time_logs.text' },
  { icon: 'bi-folder2',           titleKey: 'home.features.media_browser.title',      textKey: 'home.features.media_browser.text' },
  { icon: 'bi-tags',              titleKey: 'home.features.metadata_cleaner.title',   textKey: 'home.features.metadata_cleaner.text' },
  { icon: 'bi-mic',               titleKey: 'home.features.transcription.title',      textKey: 'home.features.transcription.text' },
  { icon: 'bi-music-note-beamed', titleKey: 'home.features.melody_extractor.title',   textKey: 'home.features.melody_extractor.text' },
  { icon: 'bi-journal-text',      titleKey: 'home.features.my_docs.title',            textKey: 'home.features.my_docs.text' },
  { icon: 'bi-people',            titleKey: 'home.features.user_management.title',    textKey: 'home.features.user_management.text', adminOnly: true },
]

const visibleFeatures = computed(() => features.filter(f => !f.adminOnly || auth.isAdmin))
</script>

<template>
  <div class="container py-3">
    <!-- Hero -->
    <div class="hero-section text-center mb-4">
      <h1 class="fw-bold mt-2 home-title">
        <i class="bi bi-music-note-beamed text-primary home-title-icon"></i>
        {{ t('home.welcome', { name: auth.username }) }}
      </h1>
      <p class="text-muted col-md-7 mx-auto mb-3 home-subtitle">
        {{ t('home.subtitle') }}<br>
      </p>
      <div class="d-inline-flex align-items-center gap-3">
        <RouterLink to="/download" class="btn btn-primary px-4">
          <i class="bi bi-cloud-arrow-down me-2"></i>{{ t('home.cta') }}
        </RouterLink>
      </div>
    </div>

    <!-- Feature cards -->
    <div class="row g-4">
      <div v-for="f in visibleFeatures" :key="f.titleKey" class="col-md-4">
        <div class="card h-100 border-0 shadow-sm feature-card">
          <div class="card-body p-4">
            <div class="feature-icon mb-3">
              <i :class="['bi', f.icon]"></i>
            </div>
            <h5 class="card-title fw-bold">{{ t(f.titleKey) }}</h5>
            <p class="card-text text-muted">{{ t(f.textKey) }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
