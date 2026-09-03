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
  authors: string[]
  institutions: string[]
  abstract: string | null
  publication: string | null
  published_at: string | null
  doi: string | null
  arxiv_id: string | null
  source_url: string | null
  keywords: string[]
  metadata_source: string | null
  page_count: number | null
  file_size: number
  status: PaperStatus
  error_message: string | null
  parse_stage?: string | null
  parse_progress?: number | null
  folder_id: string | null
  deleted_at: string | null
  last_opened_at: string | null
  created_at: string
  updated_at: string
}

export interface PaperListResponse {
  items: Paper[]
  total: number
}

export interface Folder {
  id: string
  name: string
  parent_id: string | null
  sort_order: number
  paper_count: number
  created_at: string
  updated_at: string
}

export interface FolderListResponse {
  items: Folder[]
}

export type LibraryView = 'all' | 'unfiled' | 'processing' | 'recent' | 'trash'
export type PaperSort = 'updated' | 'created' | 'title' | 'opened'

export interface PaperQuery {
  folderId?: string | null
  view?: LibraryView
  query?: string
  sort?: PaperSort
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
