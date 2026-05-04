/**
 * i18n/index.ts - Internationalisation setup for AI-Music.
 *
 * Uses vue-i18n v9 in Composition API mode (legacy: false).
 * Supported locales: English (default), French, Spanish.
 * The chosen locale is persisted in localStorage under "AI-Music-locale".
 *
 * Usage in components:
 *   import { useI18n } from 'vue-i18n'
 *   const { t } = useI18n()
 *   // template: {{ t('nav.home') }}
 *
 * To switch language programmatically, import and call setLocale().
 */

import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import es from './locales/es.json'
import fr from './locales/fr.json'

export type Locale = 'en' | 'fr' | 'es'

const SUPPORTED: Locale[] = ['en', 'fr', 'es']
const STORAGE_KEY = 'ai-music-locale'

function getInitialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY) as Locale | null
  if (stored && SUPPORTED.includes(stored)) return stored
  // Try to match the browser language
  const browser = navigator.language.slice(0, 2) as Locale
  return SUPPORTED.includes(browser) ? browser : 'en'
}

export const i18n = createI18n({
  legacy: false,          // Composition API mode — required for <script setup>
  locale: getInitialLocale(),
  fallbackLocale: 'en',
  messages: { en, fr, es },
})

/** Switch the active locale and persist the choice to localStorage. */
export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.lang = locale
}
