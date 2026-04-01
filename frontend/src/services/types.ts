/**
 * types.ts - Shared TypeScript interfaces for the AI-Powered-Music API.
 *
 * These types mirror the JSON shapes returned by the Flask backend.
 * All API service functions use these types for request/response typing.
 */

/** A single file or directory entry in the media browser. */
export interface MediaEntry {
  name: string
  rel_path: string
  is_dir: boolean
  size: number
  size_human: string
  mime: string
  mtime: string
}

/** Response from GET /api/media/files */
export interface MediaFilesResponse {
  entries: MediaEntry[]
  current_path: string
  /** Null when browsing the media root. */
  parent_path: string | null
  req_path: string
}

/** Response from GET /api/config */
export interface AppConfig {
  formats: string[]
  bitrates: string[]
}

/** Response from POST /api/download */
export interface DownloadResponse {
  success: boolean
  job_id?: string
  message?: string
  output?: string
  error?: string
}

/** Payload for POST /api/download */
export interface DownloadPayload {
  source: 'single' | 'playlist' | 'search_txt'
  format: string
  bitrate: string
  url?: string
  search_txt?: string
  output?: string
  verbose: boolean
}

/** Response from POST /api/media/delete */
export interface DeleteResponse {
  deleted: string[]
  errors: string[]
}

/** Response from POST /api/media/clean */
export interface CleanResponse {
  success: boolean
  output?: string
  error?: string
}

/** Response from GET /api/media/read/:path */
export interface MediaReadResponse {
  content: string
}

/** Response from POST /api/media/transcribe */
export interface TranscribeResponse {
  success: boolean
  output?: string
  error?: string
}

/** SSE done-event payload from GET /api/download/logs/:id */
export interface JobDoneEvent {
  success: boolean
  message: string
  error: string
  job_id: string
}

/** User role values */
export type UserRole = 'superadmin' | 'admin' | 'user' | 'viewer'

/** Roles that can be assigned via the admin API (superadmin is bootstrap-only) */
export const ASSIGNABLE_ROLES: UserRole[] = ['admin', 'user', 'viewer']

/** A user record returned by the admin API */
export interface UserRecord {
  id: number
  username: string
  role: UserRole
  is_active: boolean
  created_at: string
}

/** Response from GET /api/admin/users */
export interface AdminUsersResponse {
  users: UserRecord[]
}

/** Response from POST /api/admin/users and PUT /api/admin/users/:id */
export interface AdminUserResponse {
  success: boolean
  user?: UserRecord
  error?: string
}

/** Response from DELETE /api/admin/users/:id */
export interface AdminDeleteResponse {
  success: boolean
  error?: string
}

/** A single file or directory entry in the docs browser. */
export interface DocsEntry {
  name: string
  rel_path: string
  is_dir: boolean
  size: number
  size_human: string
  mtime: string
}

/** Response from GET /api/docs/files */
export interface DocsFilesResponse {
  entries: DocsEntry[]
  current_path: string
  /** Null when browsing the docs root. */
  parent_path: string | null
  req_path: string
}

/** Response from GET /api/docs/file/:path */
export interface DocsFileResponse {
  content: string
}

/** Response from POST /api/docs/files and PUT /api/docs/file/:path */
export interface DocsWriteResponse {
  success: boolean
  error?: string
}

/** Response from POST /api/docs/delete */
export interface DocsDeleteResponse {
  deleted: string[]
  errors: string[]
}

/** Response from POST /api/docs/rename */
export interface DocsRenameResponse {
  success: boolean
  new_path?: string
  error?: string
}

/** A single search result from GET /api/docs/search */
export interface DocsSearchResult {
  rel_path: string
  name: string
  /** True when the filename itself contains the query. */
  name_match: boolean
  /** Up to 3 HTML-safe highlighted content snippets. */
  snippets: string[]
}

/** Response from GET /api/docs/search */
export interface DocsSearchResponse {
  results: DocsSearchResult[]
}

// ── Stem Extraction ───────────────────────────────────────────────────────────

/** Separation job status values */
export type StemJobStatus = 'queued' | 'processing' | 'done' | 'failed'

/** Separation provider values */
export type StemProvider = 'demucs' | 'lalai' | 'audiosep'

/** Response from GET /api/stem/health */
export interface StemHealthResponse {
  status: string
  device: string
  active_jobs: number
  total_jobs: number
  audiosep_available: boolean
  lalai_configured: boolean
}

/** A single Demucs model descriptor from GET /api/stem/models */
export interface StemModelInfo {
  quality: string
  stems: string[]
  description?: string
}

/** Response from GET /api/stem/models */
export interface StemModelsResponse {
  models: Record<string, StemModelInfo>
  default: string
  stems: Record<string, { label: string; color: string }>
}

/** Response from POST /api/stem/separate (any provider) */
export interface StemStartResponse {
  job_id: string
  status: StemJobStatus
  provider: StemProvider
}

/** Full job status from GET /api/stem/jobs/:id */
export interface StemJob {
  job_id: string
  status: StemJobStatus
  provider: StemProvider
  progress: number
  message: string
  filename: string
  model: string
  stems_requested: string[]
  stems_produced: Record<string, string>
  error: string | null
  duration_s: number | null
}

/** Summary entry from GET /api/stem/jobs */
export interface StemJobSummary {
  job_id: string
  status: StemJobStatus
  provider: StemProvider
  filename: string
  progress: number
  stems_count: number
}

/** A single stem output file in the library */
export interface StemFile {
  filename: string
  stem_name: string
  rel_path: string
  size_mb: number
}

/** A stem output folder entry from GET /api/stem/library */
export interface StemFolder {
  name: string
  display_name: string
  audio_count: number
}

/** Response from GET /api/stem/library */
export interface StemLibraryResponse {
  folders: StemFolder[]
}

/** Response from GET /api/stem/library/:folder */
export interface StemFolderResponse {
  folder: string
  files: StemFile[]
}
