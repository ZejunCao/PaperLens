import type { Paper, PaperListResponse } from '@/types'

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

export async function fetchPapers(): Promise<PaperListResponse> {
  const res = await fetch('/api/papers')
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function uploadPaper(file: File): Promise<Paper> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/papers', { method: 'POST', body: form })
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

export async function deletePaper(id: string): Promise<void> {
  const res = await fetch(`/api/papers/${id}`, { method: 'DELETE' })
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

export async function retryParse(id: string): Promise<{ id: string; status: string }> {
  const res = await fetch(`/api/papers/${id}/parse`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export function paperAssetUrl(paperId: string, relativePath: string): string {
  return `/api/papers/${paperId}/assets/${relativePath.replace(/^\//, '')}`
}
