/**
 * router/index.ts - Vue Router configuration for AI-Music.
 *
 * Uses HTML5 history mode (no hash in URLs). A global navigation guard checks
 * authentication state before every route change: unauthenticated users are
 * redirected to /login; authenticated users trying to reach /login are sent
 * to the home page. Routes with `meta.requiresAdmin` are only accessible to
 * users with the superadmin or admin role.
 */

import { useAuthStore } from '@/stores/auth'
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
  },
  {
    path: '/download',
    name: 'Download',
    component: () => import('@/views/DownloadView.vue'),
  },
  {
    path: '/media',
    name: 'MediaFiles',
    component: () => import('@/views/MediaFilesView.vue'),
  },
  {
    path: '/media/:pathMatch(.*)*',
    name: 'MediaFilesNested',
    component: () => import('@/views/MediaFilesView.vue'),
  },
  {
    path: '/mydocs',
    name: 'MyDocs',
    component: () => import('@/views/MyDocsView.vue'),
  },
  {
    path: '/melody',
    name: 'Melody',
    component: () => import('@/views/MelodyView.vue'),
  },
  {
    path: '/music',
    name: 'Music',
    component: () => import('@/views/MusicView.vue'),
  },
  {
    path: '/queue',
    name: 'DownloadQueue',
    component: () => import('@/views/DownloadQueueView.vue'),
  },
  {
    path: '/storage',
    name: 'Storage',
    component: () => import('@/views/StorageDashboardView.vue'),
  },
  {
    path: '/mydocs/:pathMatch(.*)*',
    name: 'MyDocsNested',
    component: () => import('@/views/MyDocsView.vue'),
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/stem/demucs',
    name: 'StemDemucs',
    component: () => import('@/views/stem/DemucsView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/stem/lalai',
    name: 'StemLalai',
    component: () => import('@/views/stem/LalaiView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/stem/audiosep',
    name: 'StemAudiosep',
    component: () => import('@/views/stem/AudioSepView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/stem/library',
    name: 'StemLibrary',
    component: () => import('@/views/stem/StemLibraryView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/stem/library/:folder',
    name: 'StemPlayer',
    component: () => import('@/views/stem/StemPlayerView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    /** Catch-all: redirect unknown paths to home. */
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/**
 * Global navigation guard.
 *
 * - Public routes (/login) are always accessible.
 * - Protected routes redirect to /login when the user is not authenticated.
 * - Authenticated users are redirected away from /login to /.
 * - Routes with `meta.requiresAdmin` redirect non-admin users to /.
 */
router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // Resolve auth state on the first navigation only.
  if (!auth.initialized) {
    await auth.fetchMe()
  }

  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'Login' }
  }

  if (to.name === 'Login' && auth.isAuthenticated) {
    return { name: 'Home' }
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'Home' }
  }
})

export default router
