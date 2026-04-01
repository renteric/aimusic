/**
 * vite.config.ts - Vite build configuration for AI-Powered-Music frontend.
 *
 * In development the Vite dev server proxies all /api/ requests to the
 * backend on port 5000, so both can run simultaneously without CORS issues.
 *
 * VueI18nPlugin pre-compiles all locale JSON files at build time so that
 * vue-i18n uses the runtime-only build and never calls new Function() —
 * required to satisfy the strict Content-Security-Policy (no unsafe-eval).
 */

import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    vue(),
    VueI18nPlugin({
      // Pre-compile all locale JSON files — eliminates runtime eval() calls.
      include: resolve(__dirname, 'src/i18n/locales/*.json'),
    }),
  ],

  resolve: {
    alias: {
      /** @/... maps to src/... for clean imports everywhere. */
      '@': resolve(__dirname, 'src'),
      /**
       * Force the runtime-only vue-i18n build so the message compiler is never
       * bundled. All locale JSON files are pre-compiled at build time by the
       * VueI18nPlugin above, so the runtime compiler is never needed.
       */
      'vue-i18n': 'vue-i18n/dist/vue-i18n.runtime.esm-bundler.js',
    },
  },

  server: {
    port: 5173,
    proxy: {
      /** Proxy all /api/ calls to the backend in development. */
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },

  build: {
    sourcemap: false,
    outDir: 'dist',
  },
})
