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
  AiAnalyseResponse,
  AiCleanupResponse,
  AiTagsResponse,
  AiTranslateResponse,
  AppConfig,
  DownloadJobSummary,
  StorageStats,
  MelodyExtractResponse,
  MelodyJob,
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

/** List all in-memory download jobs (newest first). */
export const listDownloadJobs = () =>
  http.get<DownloadJobSummary[]>('/download/jobs')

/** Remove a completed download job record. */
export const removeDownloadJob = (jobId: string) =>
  http.delete<{ success: boolean }>(`/download/jobs/${jobId}`)

/** Cancel a running download job. */
export const cancelDownloadJob = (jobId: string) =>
  http.post<{ success: boolean }>(`/download/jobs/${jobId}/cancel`, {})

/** Fetch media storage usage statistics. */
export const fetchStorageStats = () =>
  http.get<StorageStats>('/media/storage')

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
  StemBounceRequest,
  StemBounceResponse,
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

  /** Mix stems at given volumes and export a new MP3. */
  bounce: (payload: StemBounceRequest) =>
    http.post<StemBounceResponse>('/stem/bounce', payload),
}

// ── Melody Extraction ─────────────────────────────────────────────────────────

export const melodyApi = {
  /**
   * Start a melody extraction job.
   * @param path      rel_path to an audio file inside the media directory.
   * @param options   Optional overrides for fmin/fmax/bpm/key/mode/harmony/hpss.
   */
  extract: (
    path: string,
    options: {
      fmin?: string
      fmax?: string
      min_note_ms?: number
      use_hpss?: boolean
      bpm?: number | null
      key?: string | null
      mode?: string | null
      harmony_mode?: string
    } = {},
  ) => http.post<MelodyExtractResponse>('/melody/extract', { path, ...options }),

  /** Poll a job by ID. */
  getJob: (jobId: string) => http.get<MelodyJob>(`/melody/jobs/${jobId}`),

  /** List all recent jobs (newest first). */
  listJobs: () => http.get<MelodyJob[]>('/melody/jobs'),

  /** Delete a job and its output files. */
  deleteJob: (jobId: string) => http.delete<{ success: boolean }>(`/melody/jobs/${jobId}`),

  /** Build the URL to download a specific output file. */
  downloadUrl: (jobId: string, filename: string) =>
    `/api/melody/download/${jobId}/${filename}`,

  /** Build the URL to download all output files as a ZIP archive. */
  downloadAllUrl: (jobId: string) => `/api/melody/download/${jobId}`,

  /** Copy all output files to the source audio's media directory. */
  saveAll: (jobId: string) =>
    http.post<{ saved: string[] }>(`/melody/jobs/${jobId}/save`),

  /** Copy one output file to the source audio's media directory. */
  saveFile: (jobId: string, filename: string) =>
    http.post<{ saved: string; filename: string }>(`/melody/jobs/${jobId}/save/${filename}`),
}

// ── AI Intelligence Layer ─────────────────────────────────────────────────────

export const aiApi = {
  /**
   * Clean and correct a raw Whisper transcript.
   * @param path  rel_path to a .md transcript file inside the media directory.
   * @param save  When true, the cleaned text overwrites the source file.
   */
  cleanup: (path: string, save = false) =>
    http.post<AiCleanupResponse>('/ai/cleanup', { path, save }),

  /**
   * Analyse a song's structure, themes, and lyrical devices.
   * @param path  rel_path to an audio file or its .md transcript.
   * @param save  When true, the analysis is saved as a sibling .analysis.md file.
   */
  analyse: (path: string, save = false) =>
    http.post<AiAnalyseResponse>('/ai/analyse', { path, save }),

  /**
   * Generate structured genre/mood/energy/tags for a media file.
   * @param path  rel_path to an audio file or its .md transcript.
   * @param save  When true, tags are saved as a sibling .tags.json file.
   */
  tags: (path: string, save = false) =>
    http.post<AiTagsResponse>('/ai/tags', { path, save }),

  /**
   * Translate song lyrics to a target language.
   * @param path            rel_path to an audio file or its .md transcript.
   * @param targetLanguage  Full language name in English (e.g. "French").
   * @param save            When true, saves a sibling .<lang>.translation.md file.
   */
  translate: (path: string, targetLanguage: string, save = false) =>
    http.post<AiTranslateResponse>('/ai/translate', {
      path,
      target_language: targetLanguage,
      save,
    }),
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
