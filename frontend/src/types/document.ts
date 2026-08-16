export type BlockType =
  | 'title'
  | 'section'
  | 'paragraph'
  | 'list_item'
  | 'formula'
  | 'table'
  | 'figure'
  | 'caption'
  | 'reference'
  | 'footer'
  | 'header'
  | 'other'

export interface Sentence {
  id: string
  text: string
  order: number
  bbox?: number[] | null
}

export interface TextSpan {
  id: string
  text: string
  bbox: number[]
  font_size: number
  font_name?: string | null
  color?: number | null
  flags: number
  /** PDF baseline y；用于跨字体垂直对齐 */
  origin_y?: number | null
  ascender?: number | null
}

export interface RichSegment {
  kind: 'text' | 'math'
  text?: string
  latex?: string
  bbox?: number[] | null
  display?: boolean
  font_size?: number | null
  origin_y?: number | null
  /** 左侧版式用的公式裁剪图；可复制 LaTeX 仍用 latex 字段 */
  image_path?: string | null
}

export interface ContentBlock {
  id: string
  type: BlockType
  page: number
  order: number
  bbox: number[]
  source_text: string
  sentences: Sentence[]
  spans: TextSpan[]
  segments?: RichSegment[]
  meta?: Record<string, unknown>
}

export interface PageImage {
  id: string
  page: number
  bbox: number[]
  path: string
  kind?: string
}

export interface PageLayout {
  page: number
  width: number
  height: number
  blocks: ContentBlock[]
  images: PageImage[]
}

export interface TocItem {
  id: string
  title: string
  page: number
  level: number
  block_id?: string | null
}

export interface DocumentModel {
  paper_id: string
  parser: string
  parser_version: string
  page_count: number
  title?: string | null
  pages: PageLayout[]
  toc: TocItem[]
  blocks: ContentBlock[]
}
