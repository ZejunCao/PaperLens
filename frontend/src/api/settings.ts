import type { PageTranslation } from '@/types/translation'

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
    return JSON.stringify(data)
  } catch {
    return res.statusText || `请求失败 (${res.status})`
  }
}

export interface LlmSettings {
  base_url: string
  api_key_set: boolean
  api_key_masked: string
  model: string
  configured: boolean
}

export interface TranslationState {
  paper_id: string
  target_lang: string
  configured: boolean
  pages: Record<string, PageTranslation>
}

export async function fetchLlmSettings(): Promise<LlmSettings> {
  const res = await fetch('/api/settings/llm')
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function saveLlmSettings(body: {
  base_url: string
  api_key: string
  model: string
}): Promise<LlmSettings> {
  const res = await fetch('/api/settings/llm', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function fetchTranslations(paperId: string): Promise<TranslationState> {
  const res = await fetch(`/api/papers/${paperId}/translations`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function translatePaperPage(
  paperId: string,
  page: number,
  signal?: AbortSignal,
): Promise<TranslationState> {
  const res = await fetch(`/api/papers/${paperId}/translations/pages/${page}`, {
    method: 'POST',
    signal,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}
