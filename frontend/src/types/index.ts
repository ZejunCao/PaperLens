export type PaperStatus = 'uploaded' | 'queued' | 'parsing' | 'ready' | 'failed'

export type ParseStage =
  | 'queued'
  | 'preparing'
  | 'extracting'
  | 'enriching'
  | 'saving'
  | 'done'
  | 'failed'
  | string

export interface Paper {
  id: string
  filename: string
  title: string | null
  page_count: number | null
  file_size: number
  status: PaperStatus
  error_message: string | null
  parse_stage?: string | null
  parse_progress?: number | null
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

export const PARSE_STAGE_LABEL: Record<string, string> = {
  queued: '排队等待',
  preparing: '准备解析',
  extracting: '提取版式与正文',
  enriching: '补全版式坐标',
  saving: '写入解析结果',
  done: '完成',
  failed: '失败',
}

export function parseStageLabel(stage: string | null | undefined): string {
  if (!stage) return ''
  return PARSE_STAGE_LABEL[stage] || stage
}
