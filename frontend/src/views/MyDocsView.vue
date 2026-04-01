<script setup lang="ts">
/**
 * MyDocsView.vue - Markdown document browser and editor.
 *
 * Two top-level modes:
 *   - List mode  : browse docs/ tree, create items, delete selected.
 *   - Editor mode: view/edit a single file with toolbar and source/preview tabs.
 *
 * Editor has two sub-modes (Source tab only):
 *   - Markdown : textarea showing raw syntax; toolbar inserts **markdown**.
 *   - Rich text: contenteditable div showing formatted text; toolbar uses
 *                execCommand; saved back to clean markdown via turndown.
 *
 * editorContent always holds the authoritative markdown source.
 */

import { docsApi } from '@/services/api'
import type { DocsEntry, DocsSearchResult } from '@/services/types'
import { useAuthStore } from '@/stores/auth'
import { marked } from 'marked'
import TurndownService from 'turndown'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

const auth = useAuthStore()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// Turndown converts HTML → clean markdown (used when leaving rich-text mode).
const td = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced', bulletListMarker: '-' })

// ── List state ────────────────────────────────────────────────────────────────

const entries = ref<DocsEntry[]>([])
const currentPath = ref('docs')
const parentPath = ref<string | null>(null)
const loading = ref(false)
const listError = ref('')
const selectedPaths = ref<Set<string>>(new Set())
const deleteRunning = ref(false)

const sortCol = ref<'name' | 'mtime'>('name')
const sortAsc = ref(true)

// ── Editor state ──────────────────────────────────────────────────────────────

const editorFile = ref<string | null>(null)
/** Authoritative markdown source — always up to date. */
const editorContent = ref('')
const editorDirty = ref(false)
const editorLoading = ref(false)
const editorSaving = ref(false)
const editorError = ref('')

/** 'source' shows the editor; 'preview' shows rendered markdown. */
const activeTab = ref<'source' | 'preview'>('preview')

/** In Source tab: 'markdown' = textarea, 'richtext' = contenteditable. */
const editorMode = ref<'markdown' | 'richtext'>('markdown')

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const richtextRef = ref<HTMLDivElement | null>(null)

// ── Color pickers ─────────────────────────────────────────────────────────────

interface ColorSwatch { label: string; value: string; cls: string }

/** Which color picker dropdown is open ('text', 'block', or null). */
const activeColorPicker = ref<'text' | 'block' | null>(null)
const lastTextColor = ref('#dc3545')
const lastBlockColor = ref('#fff3cd')

const TEXT_COLORS: ColorSwatch[] = [
  { label: 'Red',    value: '#dc3545', cls: 'txt-red'    },
  { label: 'Orange', value: '#e67e22', cls: 'txt-orange' },
  { label: 'Gold',   value: '#d4ac0d', cls: 'txt-gold'   },
  { label: 'Green',  value: '#198754', cls: 'txt-green'  },
  { label: 'Teal',   value: '#0d9488', cls: 'txt-teal'   },
  { label: 'Blue',   value: '#0d6efd', cls: 'txt-blue'   },
  { label: 'Indigo', value: '#6366f1', cls: 'txt-indigo' },
  { label: 'Purple', value: '#6f42c1', cls: 'txt-purple' },
  { label: 'Pink',   value: '#d63384', cls: 'txt-pink'   },
  { label: 'Gray',   value: '#6c757d', cls: 'txt-gray'   },
]

const BLOCK_COLORS: ColorSwatch[] = [
  { label: 'Yellow', value: '#fff3cd', cls: 'blk-yellow' },
  { label: 'Green',  value: '#d1e7dd', cls: 'blk-green'  },
  { label: 'Sky',    value: '#cff4fc', cls: 'blk-sky'    },
  { label: 'Red',    value: '#f8d7da', cls: 'blk-red'    },
  { label: 'Purple', value: '#e2d9f3', cls: 'blk-purple' },
  { label: 'Orange', value: '#ffe5d0', cls: 'blk-orange' },
  { label: 'Rose',   value: '#ffe4e6', cls: 'blk-rose'   },
  { label: 'Teal',   value: '#ccfbf1', cls: 'blk-teal'   },
  { label: 'Gray',   value: '#f8f9fa', cls: 'blk-gray'   },
  { label: 'Dark',   value: '#2d3748', cls: 'blk-dark'   },
]

function closeColorPickers(): void {
  activeColorPicker.value = null
}
onMounted(() => document.addEventListener('click', closeColorPickers))
onUnmounted(() => document.removeEventListener('click', closeColorPickers))

// ── Rename state ──────────────────────────────────────────────────────────────

const isRenaming = ref(false)
const renameValue = ref('')
const renameError = ref('')
const renameRunning = ref(false)

// ── Search ────────────────────────────────────────────────────────────────────

const searchQuery = ref('')
const searchResults = ref<DocsSearchResult[]>([])
const searchLoading = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearchInput(): void {
  if (searchTimer) clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    return
  }
  searchTimer = setTimeout(performSearch, 300)
}

async function performSearch(): Promise<void> {
  const q = searchQuery.value.trim()
  if (!q) return
  searchLoading.value = true
  try {
    const { data } = await docsApi.search(q)
    searchResults.value = data.results
  } catch {
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

function clearSearch(): void {
  searchQuery.value = ''
  searchResults.value = []
}

// ── New-item form ─────────────────────────────────────────────────────────────

const showNewForm = ref(false)
const newName = ref('')
const newType = ref<'file' | 'folder'>('file')
const newError = ref('')
const newRunning = ref(false)

// ── Computed ──────────────────────────────────────────────────────────────────

const sortedEntries = computed(() => {
  const col = sortCol.value
  return [...entries.value].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
    const av = col === 'name' ? a.name.toLowerCase() : a.mtime
    const bv = col === 'name' ? b.name.toLowerCase() : b.mtime
    const cmp = av < bv ? -1 : av > bv ? 1 : 0
    return sortAsc.value ? cmp : -cmp
  })
})

const selectedCount = computed(() => selectedPaths.value.size)
const allSelected = computed(
  () => entries.value.length > 0 && selectedCount.value === entries.value.length,
)

const renderedMarkdown = computed(() => marked.parse(editorContent.value) as string)
const editorFileName = computed(() => editorFile.value?.split('/').pop() ?? '')

// ── Rich-text sync helpers ────────────────────────────────────────────────────

/** Convert contenteditable HTML → markdown and update editorContent. */
function syncRichtextToMarkdown(): void {
  if (!richtextRef.value) return
  const md = td.turndown(richtextRef.value.innerHTML)
  if (md !== editorContent.value) {
    editorContent.value = md
    editorDirty.value = true
  }
}

/** Render editorContent into the contenteditable div. */
function populateRichtext(): void {
  if (richtextRef.value) {
    richtextRef.value.innerHTML = marked.parse(editorContent.value) as string
  }
}

// When switching tabs: sync out of richtext before leaving; populate on enter.
watch(activeTab, (newTab, oldTab) => {
  if (oldTab === 'source' && editorMode.value === 'richtext') {
    syncRichtextToMarkdown()
  }
  if (newTab === 'source' && editorMode.value === 'richtext') {
    nextTick(populateRichtext)
  }
})

// When toggling editor mode (while on Source tab): sync / populate accordingly.
watch(editorMode, (newMode, oldMode) => {
  if (activeTab.value !== 'source') return
  if (oldMode === 'richtext') syncRichtextToMarkdown()
  if (newMode === 'richtext') nextTick(populateRichtext)
})

// ── Path helpers ──────────────────────────────────────────────────────────────

function currentReqPath(): string {
  const param = route.params.pathMatch
  if (!param) return ''
  return Array.isArray(param) ? param.join('/') : param
}

function navigateTo(path: string): void {
  if (path === '') {
    router.push({ name: 'MyDocs' })
  } else {
    router.push({ name: 'MyDocsNested', params: { pathMatch: path.split('/') } })
  }
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadDirectory(path: string): Promise<void> {
  loading.value = true
  listError.value = ''
  selectedPaths.value = new Set()
  try {
    const { data } = await docsApi.listFiles(path)
    entries.value = data.entries
    currentPath.value = data.current_path
    parentPath.value = data.parent_path
  } catch {
    listError.value = 'Failed to load directory.'
  } finally {
    loading.value = false
  }
}

function loadOrOpen(path: string): void {
  if (path.endsWith('.md')) {
    openEditor(path)
  } else {
    loadDirectory(path)
  }
}

onMounted(() => loadOrOpen(currentReqPath()))
watch(
  () => route.params.pathMatch,
  () => { if (editorFile.value === null) loadOrOpen(currentReqPath()) },
)

// ── Sorting ───────────────────────────────────────────────────────────────────

function applySort(col: 'name' | 'mtime'): void {
  if (sortCol.value === col) {
    sortAsc.value = !sortAsc.value
  } else {
    sortCol.value = col
    sortAsc.value = true
  }
}

function sortIcon(col: 'name' | 'mtime'): string {
  if (sortCol.value !== col) return 'bi-arrow-down-up text-up-down-muted opacity-50'
  return sortAsc.value ? 'bi-arrow-up arrow-up-down' : 'bi-arrow-down arrow-up-down'
}

// ── Selection ─────────────────────────────────────────────────────────────────

function toggleAll(checked: boolean): void {
  selectedPaths.value = checked ? new Set(entries.value.map((e) => e.rel_path)) : new Set()
}

function toggleEntry(relPath: string, checked: boolean): void {
  const s = new Set(selectedPaths.value)
  checked ? s.add(relPath) : s.delete(relPath)
  selectedPaths.value = s
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function handleDelete(): Promise<void> {
  const paths = [...selectedPaths.value]
  if (!paths.length) return
  if (!confirm(`Permanently delete ${paths.length} item(s)?\n\n${paths.join('\n')}`)) return

  deleteRunning.value = true
  try {
    const { data } = await docsApi.deleteFiles(paths)
    if (data.errors.length) alert('Some items could not be deleted:\n' + data.errors.join('\n'))
    await loadDirectory(currentReqPath())
  } catch {
    alert('Delete request failed.')
  } finally {
    deleteRunning.value = false
  }
}

// ── New item ──────────────────────────────────────────────────────────────────

async function handleCreate(): Promise<void> {
  const name = newName.value.trim()
  if (!name) { newError.value = 'Name is required.'; return }

  const reqPath = currentReqPath()
  const fullPath = reqPath ? `${reqPath}/${name}` : name

  newRunning.value = true
  newError.value = ''
  try {
    await docsApi.createEntry(fullPath, newType.value, '')
    showNewForm.value = false
    newName.value = ''
    await loadDirectory(reqPath)
    if (newType.value === 'file') await openEditor(fullPath, 'source')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } }
    newError.value = err.response?.data?.error ?? 'Failed to create.'
  } finally {
    newRunning.value = false
  }
}

// ── Editor open / close / save ────────────────────────────────────────────────

async function openEditor(relPath: string, tab: 'preview' | 'source' = 'preview'): Promise<void> {
  editorLoading.value = true
  editorError.value = ''
  editorFile.value = relPath
  // Keep the URL in sync so the browser Back button works correctly.
  if (currentReqPath() !== relPath) navigateTo(relPath)
  editorContent.value = ''
  editorDirty.value = false
  activeTab.value = tab
  editorMode.value = 'markdown' // reset mode
  isRenaming.value = false
  try {
    const { data } = await docsApi.getFile(relPath)
    editorContent.value = data.content
  } catch {
    editorError.value = 'Failed to load file.'
  } finally {
    editorLoading.value = false
  }
}

function closeEditor(): void {
  if (editorDirty.value && !confirm('You have unsaved changes. Discard them?')) return
  // Sync richtext before discarding so we don't lose state references
  if (activeTab.value === 'source' && editorMode.value === 'richtext') syncRichtextToMarkdown()
  editorDirty.value = false
  editorFile.value = null
  router.back()
}

async function handleSave(): Promise<void> {
  if (!editorFile.value) return
  // Ensure richtext is flushed to editorContent before saving
  if (activeTab.value === 'source' && editorMode.value === 'richtext') syncRichtextToMarkdown()
  editorSaving.value = true
  editorError.value = ''
  try {
    await docsApi.updateFile(editorFile.value, editorContent.value)
    editorDirty.value = false
  } catch {
    editorError.value = 'Failed to save.'
  } finally {
    editorSaving.value = false
  }
}

// ── Rename ────────────────────────────────────────────────────────────────────

function startRename(): void {
  renameValue.value = editorFileName.value
  renameError.value = ''
  isRenaming.value = true
  nextTick(() => {
    const input = document.getElementById('renameInput') as HTMLInputElement | null
    input?.select()
  })
}

function cancelRename(): void {
  isRenaming.value = false
  renameError.value = ''
}

async function handleRename(): Promise<void> {
  const newName = renameValue.value.trim()
  if (!newName || newName === editorFileName.value) { cancelRename(); return }

  const oldPath = editorFile.value!
  const lastSlash = oldPath.lastIndexOf('/')
  const dir = lastSlash >= 0 ? oldPath.slice(0, lastSlash + 1) : ''
  const newPath = dir + newName

  renameRunning.value = true
  renameError.value = ''
  try {
    await docsApi.renameFile(oldPath, newPath)
    editorFile.value = newPath
    navigateTo(newPath)
    isRenaming.value = false
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: string } } }
    renameError.value = err.response?.data?.error ?? t('docs.rename_failed')
  } finally {
    renameRunning.value = false
  }
}

// ── Markdown textarea input ───────────────────────────────────────────────────

function onContentInput(e: Event): void {
  editorContent.value = (e.target as HTMLTextAreaElement).value
  editorDirty.value = true
}

function onRichtextInput(): void {
  editorDirty.value = true
}

// ── Internal doc link navigation ──────────────────────────────────────────────

/**
 * Resolve a relative href against the directory of the currently open file.
 * Returns null for external URLs, anchor-only links, or non-text targets.
 */
function resolveDocLink(href: string, currentFilePath: string): string | null {
  if (!href || href.startsWith('http://') || href.startsWith('https://') || href.startsWith('#')) {
    return null
  }
  const dir = currentFilePath.includes('/')
    ? currentFilePath.slice(0, currentFilePath.lastIndexOf('/') + 1)
    : ''
  // Normalize path segments (handles ./ and ../)
  const raw = (dir + href).split('/')
  const parts: string[] = []
  for (const seg of raw) {
    if (seg === '..') parts.pop()
    else if (seg !== '.') parts.push(seg)
  }
  return parts.join('/')
}

/** Handle clicks inside the rendered preview to intercept internal doc links. */
function onPreviewClick(e: MouseEvent): void {
  const anchor = (e.target as HTMLElement).closest('a')
  if (!anchor) return
  const href = anchor.getAttribute('href')
  if (!href) return
  const resolved = resolveDocLink(href, editorFile.value ?? '')
  if (resolved) {
    e.preventDefault()
    openEditor(resolved)
  }
}

// ── Toolbar helpers ───────────────────────────────────────────────────────────

/** Insert markdown syntax around the current textarea selection. */
function wrapSelection(before: string, after: string, placeholder = 'text'): void {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const selected = editorContent.value.slice(start, end) || placeholder
  editorContent.value =
    editorContent.value.slice(0, start) + before + selected + after + editorContent.value.slice(end)
  editorDirty.value = true
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(start + before.length, start + before.length + selected.length)
  })
}

/** Prepend a line prefix at the current line in the textarea. */
function prefixLine(prefix: string): void {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const lineStart = editorContent.value.lastIndexOf('\n', start - 1) + 1
  editorContent.value =
    editorContent.value.slice(0, lineStart) + prefix + editorContent.value.slice(lineStart)
  editorDirty.value = true
  nextTick(() => {
    ta.focus()
    ta.setSelectionRange(lineStart + prefix.length + (start - lineStart), lineStart + prefix.length + (start - lineStart))
  })
}

function insertHRule(): void {
  const ta = textareaRef.value
  if (!ta) return
  const pos = ta.selectionStart
  editorContent.value =
    editorContent.value.slice(0, pos) + '\n\n---\n\n' + editorContent.value.slice(pos)
  editorDirty.value = true
  nextTick(() => { ta.focus() })
}

/** Apply a text foreground color (CSS class) to the current selection. */
function applyTextColor(swatch: ColorSwatch | null): void {
  activeColorPicker.value = null
  if (swatch) lastTextColor.value = swatch.value
  if (editorMode.value === 'richtext') {
    rtCmd('foreColor', swatch?.value ?? 'inherit')
    return
  }
  if (swatch) wrapSelection(`<span class="${swatch.cls}">`, '</span>')
}

/**
 * Apply a background color to the code block at the cursor, or wrap the
 * current selection in a styled div if no code block is found.
 *
 * Handles three cases in markdown mode:
 *   1. Cursor inside a fenced ```…``` block → replaces it with a styled <pre>.
 *   2. Cursor inside an existing <pre style="…"> → re-colors it.
 *   3. Fallback → wraps selected text in a styled <div>.
 */
function applyBlockColor(swatch: ColorSwatch | null): void {
  activeColorPicker.value = null
  if (swatch) lastBlockColor.value = swatch.value
  if (editorMode.value === 'richtext') {
    rtCmd('hiliteColor', swatch?.value ?? 'transparent')
    return
  }
  const ta = textareaRef.value
  if (!ta) return
  const pos = ta.selectionStart
  const selEnd = ta.selectionEnd
  const content = editorContent.value

  // Case 1: cursor inside a fenced code block
  const fenceRe = /^```[^\n]*\n([\s\S]*?)^```/gm
  let m: RegExpExecArray | null
  while ((m = fenceRe.exec(content)) !== null) {
    if (pos >= m.index && pos <= m.index + m[0].length) {
      const inner = m[1].trimEnd()
      const replacement = swatch
        ? `<pre class="${swatch.cls}"><code>${inner}</code></pre>`
        : `\`\`\`\n${inner}\n\`\`\``
      editorContent.value = content.slice(0, m.index) + replacement + content.slice(m.index + m[0].length)
      editorDirty.value = true
      nextTick(() => ta.focus())
      return
    }
  }

  // Case 2: cursor inside an existing <pre class="..."> block
  const preRe = /<pre[^>]*>\s*<code>([\s\S]*?)<\/code>\s*<\/pre>/g
  while ((m = preRe.exec(content)) !== null) {
    if (pos >= m.index && pos <= m.index + m[0].length) {
      const inner = m[1]
      const replacement = swatch
        ? `<pre class="${swatch.cls}"><code>${inner}</code></pre>`
        : `\`\`\`\n${inner.trim()}\n\`\`\``
      editorContent.value = content.slice(0, m.index) + replacement + content.slice(m.index + m[0].length)
      editorDirty.value = true
      nextTick(() => ta.focus())
      return
    }
  }

  // Case 3: wrap selection in a colored div
  if (swatch) {
    const selected = content.slice(pos, selEnd)
    const wrapped = `<div class="${swatch.cls}">${selected || 'text'}</div>`
    editorContent.value = content.slice(0, pos) + wrapped + content.slice(selEnd)
    editorDirty.value = true
  }
}

/** Run a contenteditable execCommand (rich-text mode). */
function rtCmd(cmd: string, value?: string): void {
  richtextRef.value?.focus()
  document.execCommand(cmd, false, value)
  editorDirty.value = true
}

interface ToolbarButton {
  icon: string
  title: string
  action: () => void
}

/** Each button dispatches to markdown or execCommand depending on editorMode. */
const toolbar: ToolbarButton[] = [
  {
    icon: 'bi-type-bold',
    title: 'Bold',
    action: () => editorMode.value === 'richtext' ? rtCmd('bold') : wrapSelection('**', '**'),
  },
  {
    icon: 'bi-type-italic',
    title: 'Italic',
    action: () => editorMode.value === 'richtext' ? rtCmd('italic') : wrapSelection('*', '*'),
  },
  {
    icon: 'bi-type-h1',
    title: 'Heading 1',
    action: () => editorMode.value === 'richtext' ? rtCmd('formatBlock', 'h1') : prefixLine('# '),
  },
  {
    icon: 'bi-type-h2',
    title: 'Heading 2',
    action: () => editorMode.value === 'richtext' ? rtCmd('formatBlock', 'h2') : prefixLine('## '),
  },
  {
    icon: 'bi-type-h3',
    title: 'Heading 3',
    action: () => editorMode.value === 'richtext' ? rtCmd('formatBlock', 'h3') : prefixLine('### '),
  },
  {
    icon: 'bi-link-45deg',
    title: 'Link',
    action: () => {
      if (editorMode.value === 'richtext') {
        const url = prompt('URL:')
        if (url) rtCmd('createLink', url)
      } else {
        wrapSelection('[', '](url)')
      }
    },
  },
  {
    icon: 'bi-list-ul',
    title: 'Bullet list',
    action: () => editorMode.value === 'richtext' ? rtCmd('insertUnorderedList') : prefixLine('- '),
  },
  {
    icon: 'bi-list-ol',
    title: 'Numbered list',
    action: () => editorMode.value === 'richtext' ? rtCmd('insertOrderedList') : prefixLine('1. '),
  },
  {
    icon: 'bi-code',
    title: 'Inline code',
    action: () => editorMode.value === 'richtext' ? rtCmd('formatBlock', 'pre') : wrapSelection('`', '`'),
  },
  {
    icon: 'bi-code-square',
    title: 'Code block',
    action: () => editorMode.value === 'richtext' ? rtCmd('formatBlock', 'pre') : wrapSelection('```\n', '\n```', 'code'),
  },
  {
    icon: 'bi-chat-square-quote',
    title: 'Blockquote',
    action: () => editorMode.value === 'richtext' ? rtCmd('formatBlock', 'blockquote') : prefixLine('> '),
  },
  {
    icon: 'bi-dash-lg',
    title: 'Horizontal rule',
    action: () => editorMode.value === 'richtext' ? rtCmd('insertHorizontalRule') : insertHRule(),
  },
]
</script>

<template>
  <div class="container py-4">

    <!-- ── EDITOR MODE ──────────────────────────────────────────────────────── -->
    <template v-if="editorFile !== null">

      <!-- Header bar -->
      <div class="d-flex align-items-center gap-2 mb-3 flex-wrap">
        <!-- Back -->
        <button class="btn btn-outline-secondary btn-sm" @click="closeEditor">
          <i class="bi bi-arrow-left me-1"></i>{{ t('common.back') }}
        </button>

        <!-- Filename / rename -->
        <div v-if="isRenaming && !auth.isViewer" class="d-flex align-items-center gap-1 flex-grow-1">
          <input
            id="renameInput"
            v-model="renameValue"
            class="form-control form-control-sm font-monospace doc-rename-input"
            @keydown.enter="handleRename"
            @keydown.esc="cancelRename"
          />
          <button class="btn btn-sm btn-success" :disabled="renameRunning" @click="handleRename" :title="t('docs.confirm_rename')">
            <span v-if="renameRunning" class="spinner-border spinner-border-sm"></span>
            <i v-else class="bi bi-check-lg"></i>
          </button>
          <button class="btn btn-sm btn-outline-secondary" @click="cancelRename" :title="t('docs.cancel_rename')">
            <i class="bi bi-x-lg"></i>
          </button>
          <span v-if="renameError" class="text-danger small ms-1">{{ renameError }}</span>
        </div>
        <div v-else class="d-flex align-items-center gap-1 flex-grow-1 min-w-0">
          <span class="text-muted small font-monospace text-truncate">{{ editorFile }}</span>
          <button
            v-if="!auth.isViewer"
            class="btn btn-link btn-sm p-0 ms-1 flex-shrink-0 opacity-50"
            :title="t('docs.rename_file')"
            @click="startRename"
          >
            <i class="bi bi-pencil-square small"></i>
          </button>
        </div>

        <!-- Unsaved badge -->
        <span v-if="editorDirty" class="badge bg-warning text-dark">{{ t('docs.unsaved') }}</span>

        <!-- Save -->
        <button
          class="btn btn-sm btn-primary"
          :disabled="editorSaving || !editorDirty"
          @click="handleSave"
        >
          <span v-if="editorSaving" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-floppy me-1"></i>
          {{ editorSaving ? t('common.saving') : t('common.save') }}
        </button>
      </div>

      <!-- Error -->
      <div v-if="editorError" class="alert alert-danger py-2 small">{{ editorError }}</div>

      <!-- Editor card -->
      <div class="card border-0 shadow-sm">

        <!-- Card header: Source/Preview tabs + mode switch -->
        <div class="card-header py-2 d-flex align-items-center gap-3 flex-wrap">
          <ul class="nav nav-pills gap-1 mb-0">
            <li class="nav-item">
              <button
                class="nav-link py-1 px-3"
                :class="{ active: activeTab === 'source' }"
                @click="activeTab = 'source'"
              >
                <i class="bi bi-code me-1"></i>{{ t('docs.source_tab') }}
              </button>
            </li>
            <li class="nav-item">
              <button
                class="nav-link py-1 px-3"
                :class="{ active: activeTab === 'preview' }"
                @click="activeTab = 'preview'"
              >
                <i class="bi bi-eye me-1"></i>{{ t('docs.preview_tab') }}
              </button>
            </li>
          </ul>

          <!-- Mode switch — only in Source tab, non-viewer -->
          <div v-if="activeTab === 'source' && !auth.isViewer" class="ms-auto d-flex align-items-center gap-2">
            <span class="small text-muted" :class="{ 'fw-semibold text-dark': editorMode === 'markdown' }">{{ t('docs.markdown_mode') }}</span>
            <div class="form-check form-switch mb-0">
              <input
                id="editorModeSwitch"
                class="form-check-input"
                type="checkbox"
                :checked="editorMode === 'richtext'"
                @change="editorMode = ($event.target as HTMLInputElement).checked ? 'richtext' : 'markdown'"
              />
            </div>
            <span class="small text-muted" :class="{ 'fw-semibold text-dark': editorMode === 'richtext' }">{{ t('docs.richtext_mode') }}</span>
          </div>
        </div>

        <!-- Toolbar — always visible in Source tab (non-viewer) -->
        <div
          v-if="activeTab === 'source' && !auth.isViewer"
          class="doc-toolbar px-2 py-1 d-flex flex-wrap gap-1 border-bottom"
        >
          <button
            v-for="btn in toolbar"
            :key="btn.title"
            class="btn btn-outline-secondary btn-sm"
            :title="btn.title"
            type="button"
            @click="btn.action"
          >
            <i :class="['bi', btn.icon]"></i>
          </button>

          <!-- Separator -->
          <span class="doc-toolbar-sep"></span>

          <!-- Text color picker -->
          <div class="position-relative" @click.stop>
            <button
              class="btn btn-outline-secondary btn-sm doc-color-btn"
              title="Text color"
              type="button"
              @click="activeColorPicker = activeColorPicker === 'text' ? null : 'text'"
            >
              <i class="bi bi-fonts"></i>
              <span class="doc-color-dot" :style="{ background: lastTextColor }"></span>
            </button>
            <div v-if="activeColorPicker === 'text'" class="doc-color-grid">
              <button
                v-for="c in TEXT_COLORS"
                :key="c.value"
                class="doc-color-swatch"
                :style="{ background: c.value }"
                :title="c.label"
                @click="applyTextColor(c)"
              ></button>
              <button class="doc-color-swatch doc-color-clear" title="Remove color" @click="applyTextColor(null)">✕</button>
            </div>
          </div>

          <!-- Block background color picker -->
          <div class="position-relative" @click.stop>
            <button
              class="btn btn-outline-secondary btn-sm doc-color-btn"
              title="Block background color"
              type="button"
              @click="activeColorPicker = activeColorPicker === 'block' ? null : 'block'"
            >
              <i class="bi bi-paint-bucket"></i>
              <span class="doc-color-dot" :style="{ background: lastBlockColor }"></span>
            </button>
            <div v-if="activeColorPicker === 'block'" class="doc-color-grid">
              <button
                v-for="c in BLOCK_COLORS"
                :key="c.value"
                class="doc-color-swatch"
                :style="{ background: c.value }"
                :title="c.label"
                @click="applyBlockColor(c)"
              ></button>
              <button class="doc-color-swatch doc-color-clear" title="Default style" @click="applyBlockColor(null)">✕</button>
            </div>
          </div>
        </div>

        <!-- Content area -->
        <div class="card-body p-0">

          <!-- Loading spinner -->
          <div v-if="editorLoading" class="text-center py-5">
            <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
          </div>

          <!-- Source + Markdown mode: raw textarea -->
          <textarea
            v-else-if="activeTab === 'source' && editorMode === 'markdown'"
            ref="textareaRef"
            class="doc-source"
            :value="editorContent"
            @input="onContentInput"
            spellcheck="false"
            :placeholder="t('docs.placeholder')"
          ></textarea>

          <!-- Source + Rich text mode: contenteditable (formatted, no syntax) -->
          <div
            v-else-if="activeTab === 'source' && editorMode === 'richtext'"
            ref="richtextRef"
            class="doc-richtext doc-preview"
            contenteditable="true"
            @input="onRichtextInput"
          ></div>

          <!-- Preview: read-only rendered markdown; internal links open in editor -->
          <div
            v-else
            class="doc-preview p-4"
            v-html="renderedMarkdown"
            @click="onPreviewClick"
          ></div>
        </div>
      </div>
    </template>

    <!-- ── LIST MODE ─────────────────────────────────────────────────────────── -->
    <template v-else>

      <!-- Header -->
      <div class="mb-3">
        <h2 class="mb-0 fw-bold">
          <i class="bi bi-journal-text me-2 text-primary"></i>{{ t('docs.title') }}
        </h2>
        <code class="text-muted small">/{{ currentPath }}</code>
      </div>

      <!-- Up / New / Search row -->
      <div class="d-flex align-items-center gap-2 mb-3">
        <button
          v-if="parentPath !== null"
          class="btn btn-outline-secondary btn-sm flex-shrink-0"
          @click="navigateTo(parentPath ?? '')"
        >
          <i class="bi bi-arrow-up me-1"></i>{{ t('common.up') }}
        </button>
        <button
          v-if="!auth.isViewer"
          class="btn btn-outline-primary btn-sm flex-shrink-0"
          @click="showNewForm = !showNewForm; newError = ''"
        >
          <i class="bi bi-plus-lg me-1"></i>{{ t('common.new') }}
        </button>
        <div class="input-group">
          <span class="input-group-text bg-white border-end-0">
            <span v-if="searchLoading" class="spinner-border spinner-border-sm text-muted"></span>
            <i v-else class="bi bi-search text-muted"></i>
          </span>
          <input
            v-model="searchQuery"
            type="search"
            class="form-control border-start-0 ps-0"
            :placeholder="t('docs.search_placeholder')"
            @input="onSearchInput"
          />
          <button
            v-if="searchQuery"
            class="btn btn-outline-secondary"
            type="button"
            @click="clearSearch"
            title="Clear search"
          >
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
      </div>

      <!-- Search results -->
      <div v-if="searchQuery.trim()">
        <div v-if="!searchLoading && searchResults.length === 0" class="text-center py-5 text-muted">
          <i class="bi bi-search display-6 d-block mb-2"></i>
          {{ t('docs.no_results', { query: searchQuery }) }}
        </div>
        <div v-else class="d-flex flex-column gap-2">
          <div
            v-for="result in searchResults"
            :key="result.rel_path"
            class="card border-0 shadow-sm search-result-card"
            @click="openEditor(result.rel_path)"
            role="button"
          >
            <div class="card-body py-2 px-3">
              <div class="d-flex align-items-center gap-2 mb-1">
                <i class="bi bi-file-earmark-text text-primary flex-shrink-0"></i>
                <span class="fw-semibold text-truncate">{{ result.name }}</span>
                <span v-if="result.name_match" class="badge bg-primary-subtle text-primary-emphasis ms-1 flex-shrink-0">name</span>
                <span class="text-muted small ms-auto text-truncate font-monospace flex-shrink-0 doc-search-path">{{ result.rel_path }}</span>
              </div>
              <div
                v-for="(snippet, i) in result.snippets"
                :key="i"
                class="search-snippet text-muted small font-monospace"
                v-html="snippet"
              ></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Normal directory listing (hidden during search) -->
      <template v-else>

      <!-- New item form -->
      <div v-if="showNewForm && !auth.isViewer" class="card border-0 shadow-sm mb-3">
        <div class="card-body py-3">
          <div class="d-flex gap-2 align-items-end flex-wrap">
            <div>
              <label class="form-label small mb-1">{{ t('docs.new_type_label') }}</label>
              <select v-model="newType" class="form-select form-select-sm">
                <option value="file">{{ t('docs.new_file_option') }}</option>
                <option value="folder">{{ t('docs.new_folder_option') }}</option>
              </select>
            </div>
            <div class="flex-grow-1 doc-new-name">
              <label class="form-label small mb-1">{{ t('docs.new_name_label') }}</label>
              <input
                v-model="newName"
                class="form-control form-control-sm"
                :placeholder="newType === 'file' ? 'Notes.md' : 'folder-name'"
                @keydown.enter="handleCreate"
                autofocus
              />
            </div>
            <button class="btn btn-sm btn-primary" :disabled="newRunning" @click="handleCreate">
              <span v-if="newRunning" class="spinner-border spinner-border-sm me-1"></span>
              {{ t('common.create') }}
            </button>
            <button class="btn btn-sm btn-outline-secondary" @click="showNewForm = false">
              {{ t('common.cancel') }}
            </button>
          </div>
          <div v-if="newError" class="text-danger small mt-1">{{ newError }}</div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="listError" class="alert alert-danger">{{ listError }}</div>

      <!-- File table -->
      <div class="card border-0 shadow-sm">
        <div class="card-body p-0">
          <div class="table-responsive">
            <table class="table table-hover align-middle mb-0">
              <thead class="table-light">
                <tr>
                  <th v-if="!auth.isViewer" class="col-checkbox">
                    <input
                      type="checkbox"
                      class="form-check-input"
                      :checked="allSelected"
                      :indeterminate="selectedCount > 0 && !allSelected"
                      @change="toggleAll(($event.target as HTMLInputElement).checked)"
                    />
                  </th>
                  <th class="sortable-col" @click="applySort('name')">
                    {{ t('common.name') }} <i :class="['bi', sortIcon('name')]"></i>
                  </th>
                  <th class="sortable-col" @click="applySort('mtime')">
                    {{ t('common.modified') }} <i :class="['bi', sortIcon('mtime')]"></i>
                  </th>
                  <th class="col-actions">{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="loading">
                  <td :colspan="auth.isViewer ? 3 : 4" class="text-center py-4">
                    <span class="spinner-border spinner-border-sm me-2"></span>{{ t('common.loading') }}
                  </td>
                </tr>

                <tr
                  v-for="entry in sortedEntries"
                  :key="entry.rel_path"
                  :class="{ 'table-active': selectedPaths.has(entry.rel_path) }"
                >
                  <td v-if="!auth.isViewer">
                    <input
                      type="checkbox"
                      class="form-check-input"
                      :checked="selectedPaths.has(entry.rel_path)"
                      @change="toggleEntry(entry.rel_path, ($event.target as HTMLInputElement).checked)"
                    />
                  </td>

                  <td>
                    <button
                      v-if="entry.is_dir"
                      class="btn btn-link p-0 text-decoration-none"
                      @click="navigateTo(entry.rel_path)"
                    >
                      <i class="bi bi-folder-fill text-warning me-1"></i>{{ entry.name }}/
                    </button>
                    <button
                      v-else
                      class="btn btn-link p-0 text-decoration-none"
                      @click="openEditor(entry.rel_path)"
                    >
                      <i class="bi bi-file-earmark-text text-primary me-1"></i>{{ entry.name }}
                    </button>
                  </td>

                  <td class="text-muted text-nowrap small">{{ entry.mtime }}</td>

                  <td>
                    <button
                      v-if="!entry.is_dir && !auth.isViewer"
                      class="btn btn-sm btn-outline-primary"
                      title="Edit"
                      @click="openEditor(entry.rel_path, 'source')"
                    >
                      <i class="bi bi-pencil"></i>
                    </button>
                    <span v-else-if="entry.is_dir" class="text-muted">—</span>
                  </td>
                </tr>

                <tr v-if="!loading && entries.length === 0">
                  <td :colspan="auth.isViewer ? 3 : 4" class="text-center py-5 text-muted">
                    <i class="bi bi-journal display-6 d-block mb-2"></i>
                    {{ t('docs.no_docs') }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="!auth.isViewer" class="card-footer d-flex justify-content-end py-2">
          <button
            class="btn btn-sm btn-danger"
            :disabled="selectedCount === 0 || deleteRunning"
            @click="handleDelete"
          >
            <span v-if="deleteRunning" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-trash me-1"></i>
            {{ selectedCount > 0 ? t('docs.delete_n', { n: selectedCount }) : t('docs.delete_selected') }}
          </button>
        </div>
      </div>

      </template> <!-- end v-else (no search query) -->
    </template>
  </div>
</template>
