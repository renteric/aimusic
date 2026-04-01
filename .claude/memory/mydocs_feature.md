---
name: My Docs feature implementation
description: /mydocs page — URL-synced file navigation, Back button behaviour, editor tab parameter, viewer restrictions
type: project
---

Markdown document browser and dual-mode editor added 2026-03-28.

**Why:** User wanted an in-app markdown notebook alongside the media library, with preview-first UX and proper browser Back-button navigation.

**How to apply:** When touching MyDocsView.vue or docs.py, follow the patterns below to avoid breaking navigation.

## Key implementation decisions

### URL sync (`openEditor` → `navigateTo`)
`openEditor(relPath)` calls `navigateTo(relPath)` when `currentReqPath() !== relPath`.
This pushes each opened file onto browser history so `router.back()` works.
Guard: `editorFile.value = relPath` is set **before** `navigateTo` so the route watcher
(which checks `editorFile.value === null`) does not re-trigger `openEditor` in a loop.

### Back button (`closeEditor` → `router.back()`)
`closeEditor` sets `editorFile.value = null` then calls `router.back()`.
The route watcher fires after navigation; since `editorFile === null` it calls
`loadOrOpen(currentReqPath())`, which reopens the previous `.md` file or loads
a directory listing depending on the URL.

### `loadOrOpen` helper
```ts
function loadOrOpen(path: string): void {
  if (path.endsWith('.md')) openEditor(path)
  else loadDirectory(path)
}
```
Used in both `onMounted` and the route watcher — handles direct URL navigation
to a `.md` file (e.g. bookmarks, page refresh).

### `openEditor` tab parameter
```ts
async function openEditor(relPath: string, tab: 'preview' | 'source' = 'preview')
```
- Filename click in listing → default `'preview'`
- Edit (pencil) button in listing → `'source'`
- In-doc link click and Back navigation → default `'preview'`

### Viewer role restrictions
Create, edit (Source tab hidden via `v-if="!auth.isViewer"`), rename, delete are hidden
for viewers. Browse and Preview tab remain accessible.
