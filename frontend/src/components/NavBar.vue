<script setup lang="ts">
/**
 * NavBar.vue - Top navigation bar for AI-Powered-Music.
 *
 * Displays the app brand, navigation links (including the Stem Extraction
 * dropdown for admin/superadmin users), a language switcher, and a logout button.
 */

import { setLocale, type Locale } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()
const { t, locale } = useI18n()

interface LanguageOption {
  code: Locale
  label: string
  flag: string
}

const languages: LanguageOption[] = [
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
  { code: 'es', label: 'Español', flag: '🇪🇸' },
]

function currentFlag(): string {
  return languages.find((l) => l.code === locale.value)?.flag ?? '🌐'
}

/** Log out and navigate to the login page. */
async function handleLogout(): Promise<void> {
  await auth.logout()
  router.push({ name: 'Login' })
}
</script>

<template>
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm">
    <div class="container">
      <!-- Brand -->
      <RouterLink class="navbar-brand fw-bold" to="/">
        <i class="bi bi-music-note-beamed me-2"></i>{{ t('common.app_name') }}
      </RouterLink>

      <!-- Mobile toggler -->
      <button
        class="navbar-toggler"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#mainNav"
        aria-controls="mainNav"
        aria-expanded="false"
        aria-label="Toggle navigation"
      >
        <span class="navbar-toggler-icon"></span>
      </button>

      <!-- Links -->
      <div class="collapse navbar-collapse" id="mainNav">
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item">
            <RouterLink class="nav-link" to="/">
              <i class="bi bi-house me-1"></i>{{ t('nav.home') }}
            </RouterLink>
          </li>
          <li class="nav-item">
            <RouterLink class="nav-link" to="/download">
              <i class="bi bi-cloud-arrow-down me-1"></i>{{ t('nav.download') }}
            </RouterLink>
          </li>
          <li class="nav-item">
            <RouterLink class="nav-link" to="/media">
              <i class="bi bi-folder2-open me-1"></i>{{ t('nav.media_files') }}
            </RouterLink>
          </li>
          <li class="nav-item">
            <RouterLink class="nav-link" to="/mydocs">
              <i class="bi bi-journal-text me-1"></i>{{ t('nav.my_docs') }}
            </RouterLink>
          </li>

          <!-- Stem Extraction dropdown (admin + superadmin only) -->
          <li v-if="auth.isAdmin" class="nav-item dropdown">
            <a
              class="nav-link dropdown-toggle"
              href="#"
              role="button"
              data-bs-toggle="dropdown"
              aria-expanded="false"
            >
              <i class="bi bi-scissors me-1"></i>{{ t('nav.stem_extraction') }}
            </a>
            <ul class="dropdown-menu dropdown-menu-dark">
              <li>
                <RouterLink class="dropdown-item" to="/stem/demucs">
                  🎛️ Demucs
                </RouterLink>
              </li>
              <li>
                <RouterLink class="dropdown-item" to="/stem/lalai">
                  🌊 LALAL.AI
                </RouterLink>
              </li>
              <li>
                <RouterLink class="dropdown-item" to="/stem/audiosep">
                  🔊 AudioSep
                </RouterLink>
              </li>
              <li><hr class="dropdown-divider" /></li>
              <li>
                <RouterLink class="dropdown-item" to="/stem/library">
                  📋 Library
                </RouterLink>
              </li>
            </ul>
          </li>

          <li v-if="auth.isAdmin" class="nav-item">
            <RouterLink class="nav-link" to="/admin">
              <i class="bi bi-people me-1"></i>{{ t('nav.admin') }}
            </RouterLink>
          </li>
        </ul>

        <!-- Right side: user info + logout + language switcher -->
        <div class="d-flex align-items-center gap-2">

          <!-- User profile link -->
          <RouterLink
            to="/profile"
            class="btn btn-outline-light btn-sm"
            :title="auth.username ?? ''"
          >
            <i class="bi bi-person"></i>
          </RouterLink>

          <!-- Logout -->
          <button class="btn btn-outline-light btn-sm" @click="handleLogout" :disabled="auth.loading">
            <i class="bi bi-box-arrow-right me-1"></i>{{ t('nav.logout') }}
          </button>

          <!-- Language switcher -->
          <div class="dropdown">
            <button
              class="btn btn-outline-light btn-sm dropdown-toggle"
              type="button"
              data-bs-toggle="dropdown"
              aria-expanded="false"
              :title="t('nav.language')"
            >
              {{ currentFlag() }}
            </button>
            <ul class="dropdown-menu dropdown-menu-dark dropdown-menu-end">
              <li v-for="lang in languages" :key="lang.code">
                <button
                  class="dropdown-item d-flex align-items-center gap-2"
                  :class="{ active: locale === lang.code }"
                  @click="setLocale(lang.code)"
                >
                  <span>{{ lang.flag }}</span>
                  <span>{{ lang.label }}</span>
                </button>
              </li>
            </ul>
          </div>

        </div>
      </div>
    </div>
  </nav>
</template>
