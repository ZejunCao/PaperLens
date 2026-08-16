export type PaperStatus = 'uploaded' | 'queued' | 'parsing' | 'ready' | 'failed'

export interface Paper {
  id: string
  filename: string
  title: string | null
  page_count: number | null
  file_size: number
  status: PaperStatus
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface PaperListResponse {
  items: Paper[]
  total: number
}

export const STATUS_LABEL: Record<PaperStatus, string> = {
  uploaded: '已上传',
  queued: '排队中',
  parsing: '解析中',
  ready: '已就绪',
  failed: '失败',
}
