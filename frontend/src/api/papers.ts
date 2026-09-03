import type {
  Folder,
  FolderListResponse,
  Paper,
  PaperListResponse,
  PaperQuery,
} from '@/types'

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    if (data?.detail?.message) return data.detail.message
    if (Array.isArray(data?.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
    }
    return JSON.stringify(data)
  } catch {
    return res.statusText || `请求失败 (${res.status})`
  }
}

export async function fetchPapers(options: PaperQuery = {}): Promise<PaperListResponse> {
  const query = new URLSearchParams()
  if (options.folderId) query.set('folder_id', options.folderId)
  if (options.view) query.set('view', options.view)
  if (options.query?.trim()) query.set('query', options.query.trim())
  if (options.sort) query.set('sort', options.sort)
  const suffix = query.size ? `?${query}` : ''
  const res = await fetch(`/api/papers${suffix}`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function uploadPaper(file: File, folderId?: string | null): Promise<Paper> {
  const form = new FormData()
  form.append('file', file)
  if (folderId) form.append('folder_id', folderId)
  const res = await fetch('/api/papers', { method: 'POST', body: form })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** 从 arXiv 链接或裸 ID 导入：服务端本地下载 PDF 后入队解析 */
export async function importPaperFromUrl(url: string, folderId?: string | null): Promise<Paper> {
  const res = await fetch('/api/papers/from-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, folder_id: folderId || null }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchPaper(id: string): Promise<Paper> {
  const res = await fetch(`/api/papers/${id}`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function renamePaper(id: string, title: string): Promise<Paper> {
  const res = await fetch(`/api/papers/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function movePaper(id: string, folderId: string | null): Promise<Paper> {
  const res = await fetch(`/api/papers/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function deletePaper(id: string): Promise<void> {
  const res = await fetch(`/api/papers/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function restorePaper(id: string): Promise<Paper> {
  const res = await fetch(`/api/papers/${id}/restore`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function permanentlyDeletePaper(id: string): Promise<void> {
  const res = await fetch(`/api/papers/${id}/permanent`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function markPaperOpened(id: string): Promise<void> {
  const res = await fetch(`/api/papers/${id}/opened`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function fetchFolders(): Promise<FolderListResponse> {
  const res = await fetch('/api/folders')
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function createFolder(name: string, parentId: string | null): Promise<Folder> {
  const res = await fetch('/api/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id: parentId }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function updateFolder(
  id: string,
  changes: { name?: string; parent_id?: string | null; sort_order?: number },
): Promise<Folder> {
  const res = await fetch(`/api/folders/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function deleteFolder(id: string): Promise<void> {
  const res = await fetch(`/api/folders/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseError(res))
}

export function paperFileUrl(id: string): string {
  return `/api/papers/${id}/file`
}

export async function fetchDocument(id: string): Promise<import('@/types/document').DocumentModel> {
  const res = await fetch(`/api/papers/${id}/document`, { cache: 'no-store' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchDocumentChunk(
  id: string,
  startPage: number,
  pageLimit: number,
  options?: { includeManifest?: boolean; signal?: AbortSignal },
): Promise<import('@/types/document').DocumentChunk> {
  const query = new URLSearchParams({
    start_page: String(startPage),
    page_limit: String(pageLimit),
    include_manifest: String(!!options?.includeManifest),
  })
  const res = await fetch(`/api/papers/${id}/document/chunk?${query}`, {
    cache: 'no-store',
    signal: options?.signal,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function retryParse(id: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`/api/papers/${id}/parse`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export function paperAssetUrl(paperId: string, relativePath: string): string {
  return `/api/papers/${paperId}/assets/${relativePath.replace(/^\//, '')}`
}
