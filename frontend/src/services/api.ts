/**
 * api.ts - Axios instance and typed API service functions.
 *
 * All HTTP calls to the Flask backend go through this module.
 * A response interceptor automatically redirects to /login on HTTP 401
 * so every view gets this behaviour for free.
 */

import axios from 'axios'
import type {
  AdminDeleteResponse,
  AdminUserResponse,
  AdminUsersResponse,
  AppConfig,
  CleanResponse,
  DeleteResponse,
  DocsDeleteResponse,
  DocsFileResponse,
  DocsFilesResponse,
  DocsRenameResponse,
  DocsSearchResponse,
  DocsWriteResponse,
  DownloadPayload,
  DownloadResponse,
  MediaFilesResponse,
  MediaReadResponse,
  TranscribeResponse,
  UserRole,
} from './types'

/** Axios instance with credentials included for session cookie transport. */
const http = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

/** Redirect to /login on any 401 response. */
http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authApi = {
  /**
   * Check the current session.
   * @returns `{ authenticated, username?, role? }` — always HTTP 200.
   */
  me: () => http.get<{ authenticated: boolean; username?: string; role?: UserRole }>('/auth/me'),

  /** Start a session with username and password. */
  login: (username: string, password: string) =>
    http.post<{ success: boolean; username?: string; role?: UserRole; error?: string }>('/auth/login', {
      username,
      password,
    }),

  /** End the current session. */
  logout: () => http.post<{ success: boolean }>('/auth/logout'),

  /** Change the logged-in user's password. */
  changePassword: (currentPassword: string, newPassword: string) =>
    http.post<{ success: boolean; error?: string }>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
}

// ── Config ────────────────────────────────────────────────────────────────────

/** Fetch supported formats and bitrates from the server. */
export const fetchConfig = () => http.get<AppConfig>('/config')

// ── Download ──────────────────────────────────────────────────────────────────

/** Start a download job. Returns a job_id when verbose=true. */
export const startDownload = (payload: DownloadPayload) =>
  http.post<DownloadResponse>('/download', payload)

// ── Media ─────────────────────────────────────────────────────────────────────

export const mediaApi = {
  /** List a media directory. Pass an empty string for the root. */
  listFiles: (reqPath: string) =>
    http.get<MediaFilesResponse>(`/media/files${reqPath ? `/${reqPath}` : ''}`),

  /** Delete files or folders by their rel_path values. */
  deleteFiles: (paths: string[]) =>
    http.post<DeleteResponse>('/media/delete', { paths }),

  /** Run the metadata cleaner on a path. */
  cleanMetadata: (params: {
    path: string
    show?: boolean
    clean?: boolean
    backup?: boolean
    recursive?: boolean
    remove_protection?: boolean
  }) => http.post<CleanResponse>('/media/clean', params),

  /** Transcribe an audio file. */
  transcribe: (path: string, language = 'Spanish', model = 'base') =>
    http.post<TranscribeResponse>('/media/transcribe', { path, language, model }),

  /** Fetch the raw Markdown content of a .md file. */
  readFile: (relPath: string) =>
    http.get<MediaReadResponse>(`/media/read/${relPath}`),

  /** Build the streaming URL for an audio file. */
  streamUrl: (relPath: string) => `/api/media/stream/${relPath}`,

  /** Build the download URL for a file. */
  downloadUrl: (relPath: string) => `/api/media/download/${relPath}`,
}

// ── Admin ──────────────────────────────────────────────────────────────────────

export const adminApi = {
  /** List all user accounts. */
  listUsers: () => http.get<AdminUsersResponse>('/admin/users'),

  /** Create a new user. */
  createUser: (username: string, password: string, role: UserRole) =>
    http.post<AdminUserResponse>('/admin/users', { username, password, role }),

  /** Update a user account. */
  updateUser: (
    id: number,
    fields: { username?: string; password?: string; role?: UserRole; is_active?: boolean },
  ) => http.put<AdminUserResponse>(`/admin/users/${id}`, fields),

  /** Delete a user account. */
  deleteUser: (id: number) => http.delete<AdminDeleteResponse>(`/admin/users/${id}`),
}

// ── Stem Extraction ───────────────────────────────────────────────────────────

import type {
  StemFolderResponse,
  StemHealthResponse,
  StemJob,
  StemJobSummary,
  StemLibraryResponse,
  StemModelsResponse,
  StemStartResponse,
} from './types'

export const stemApi = {
  /** Separator health check — returns device info. */
  health: () => http.get<StemHealthResponse>('/stem/health'),

  /** List available Demucs models and stem definitions. */
  models: () => http.get<StemModelsResponse>('/stem/models'),

  /** Start a Demucs separation job. */
  separateDemucs: (file: File, model: string, stems?: string[]) => {
    const form = new FormData()
    form.append('file', file)
    const params = new URLSearchParams({ model })
    if (stems?.length) params.set('stems', stems.join(','))
    return http.post<StemStartResponse>(`/stem/separate?${params}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  /** Start a LALAL.AI separation job. */
  separateLalai: (file: File, stems?: string[]) => {
    const form = new FormData()
    form.append('file', file)
    const params = new URLSearchParams()
    if (stems?.length) params.set('stems', stems.join(','))
    const qs = params.toString() ? `?${params}` : ''
    return http.post<StemStartResponse>(`/stem/lalai/separate${qs}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  /** Start an AudioSep separation job. */
  separateAudiosep: (file: File, stems?: string[]) => {
    const form = new FormData()
    form.append('file', file)
    const params = new URLSearchParams()
    if (stems?.length) params.set('stems', stems.join(','))
    const qs = params.toString() ? `?${params}` : ''
    return http.post<StemStartResponse>(`/stem/audiosep/separate${qs}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  /** Poll a job for status + results. */
  getJob: (jobId: string) => http.get<StemJob>(`/stem/jobs/${jobId}`),

  /** List all jobs. */
  listJobs: () => http.get<StemJobSummary[]>('/stem/jobs'),

  /** Delete a job and its output files. */
  deleteJob: (jobId: string) => http.delete<{ message: string }>(`/stem/jobs/${jobId}`),

  /** List stem output folders (Library). */
  library: () => http.get<StemLibraryResponse>('/stem/library'),

  /** List files inside a Library folder. */
  libraryFolder: (folder: string) => http.get<StemFolderResponse>(`/stem/library/${folder}`),

  /** Delete a Library folder. */
  deleteFolder: (folder: string) => http.delete<{ message: string }>(`/stem/library/${folder}`),

  /** Build the URL to download a single stem. */
  downloadStemUrl: (jobId: string, stemName: string) =>
    `/api/stem/download/${jobId}/${stemName}`,

  /** Build the URL to download all stems as ZIP. */
  downloadAllUrl: (jobId: string) => `/api/stem/download/${jobId}`,
}

// ── Docs ──────────────────────────────────────────────────────────────────────

export const docsApi = {
  /** List a docs directory. Pass an empty string for the root. */
  listFiles: (reqPath: string) =>
    http.get<DocsFilesResponse>(`/docs/files${reqPath ? `/${reqPath}` : ''}`),

  /** Get the text content of a docs file. */
  getFile: (relPath: string) => http.get<DocsFileResponse>(`/docs/file/${relPath}`),

  /** Create a new file or folder. */
  createEntry: (path: string, type: 'file' | 'folder', content: string) =>
    http.post<DocsWriteResponse>('/docs/files', { path, type, content }),

  /** Overwrite a file's content. */
  updateFile: (relPath: string, content: string) =>
    http.put<DocsWriteResponse>(`/docs/file/${relPath}`, { content }),

  /** Delete files or folders by their rel_path values. */
  deleteFiles: (paths: string[]) =>
    http.post<DocsDeleteResponse>('/docs/delete', { paths }),

  /** Rename or move a file or folder. */
  renameFile: (from: string, to: string) =>
    http.post<DocsRenameResponse>('/docs/rename', { from, to }),

  /** Search docs by filename and content. */
  search: (q: string) =>
    http.get<DocsSearchResponse>('/docs/search', { params: { q } }),
}
