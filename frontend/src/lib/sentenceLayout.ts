import type { ContentBlock, PageLayout, RichSegment, TextSpan } from '@/types/document'

export function mathUnitKey(bbox: number[]): string {
  return `m:${bbox.map((n) => Math.round(n * 10) / 10).join(',')}`
}

export type SentRange = { id: string; start: number; end: number }

export type UnitAlign = { ids: string[]; ranges: SentRange[] }

/** 去掉空白/标点，避免 PDF 拆开的 [54, 45] 与重复逗号导致整句匹配失败 */
export function foldText(s: string): string {
  return (s || '')
    .normalize('NFKC')
    .replace(/[\u2018\u2019\u201A\u201B]/g, "'")
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, '')
}

function looksLikeLatex(text: string): boolean {
  return /\\[a-zA-Z]+/.test(text)
}

type Unit = { key: string; text: string; y: number; x: number }

/**
 * 解析器保留了 span 的阅读顺序。若相邻 span 从页面左下明显跳回右上，
 * 说明同一个段落/句子跨栏；此时不能再单纯按 y 排序。
 */
function blockColumnSplit(block: ContentBlock): number | null {
  const spans = (block.spans || []).filter((span) => span.bbox?.length >= 4)
  let best: { reset: number; split: number } | null = null
  for (let i = 1; i < spans.length; i++) {
    const prev = spans[i - 1]!
    const next = spans[i]!
    const [px0 = 0, py0 = 0, px1 = px0] = prev.bbox
    const [nx0 = 0, ny0 = 0] = next.bbox
    const verticalReset = py0 - ny0
    const horizontalJump = nx0 - px0
    if (verticalReset < 24 || horizontalJump < 80) continue
    const split = (px1 + nx0) / 2
    if (!best || verticalReset > best.reset) best = { reset: verticalReset, split }
  }
  return best?.split ?? null
}

function blockUnits(block: ContentBlock): Unit[] {
  const items: Unit[] = []
  for (const span of block.spans || []) {
    if (looksLikeLatex(span.text || '')) continue
    items.push({
      key: span.id,
      text: span.text || '',
      y: span.bbox[1] ?? 0,
      x: span.bbox[0] ?? 0,
    })
  }
  for (const seg of block.segments || []) {
    if (seg.kind !== 'math' || !seg.bbox || seg.bbox.length < 4) continue
    if (!(seg.latex || seg.text || '').trim()) continue
    items.push({
      key: mathUnitKey(seg.bbox),
      text: seg.latex || seg.text || '',
      y: seg.bbox[1],
      x: seg.bbox[0],
    })
  }
  const columnSplit = blockColumnSplit(block)
  items.sort((a, b) => {
    if (columnSplit != null) {
      const aColumn = a.x < columnSplit ? 0 : 1
      const bColumn = b.x < columnSplit ? 0 : 1
      if (aColumn !== bColumn) return aColumn - bColumn
    }
    return Math.abs(a.y - b.y) > 2 ? a.y - b.y : a.x - b.x
  })
  return items
}

type HayCell = { key: string; orig: number }

function toRanges(ids: (string | '')[]): SentRange[] {
  const ranges: SentRange[] = []
  let i = 0
  while (i < ids.length) {
    const id = ids[i]
    if (!id) {
      i++
      continue
    }
    let j = i + 1
    while (j < ids.length && ids[j] === id) j++
    ranges.push({ id, start: i, end: j })
    i = j
  }
  return ranges
}

function fillOrig(len: number, marked: Map<number, string>): string[] {
  const arr: string[] = Array.from({ length: len }, () => '')
  for (const [i, id] of marked) {
    if (i >= 0 && i < len) arr[i] = id
  }
  let last = ''
  for (let i = 0; i < len; i++) {
    if (arr[i]) last = arr[i]
    else if (last) arr[i] = last
  }
  let next = ''
  for (let i = len - 1; i >= 0; i--) {
    if (arr[i]) next = arr[i]
    else if (next) arr[i] = next
  }
  return arr
}

function mapBlock(block: ContentBlock): Map<string, UnitAlign> {
  const out = new Map<string, UnitAlign>()
  const sents = [...(block.sentences || [])]
    .filter((s) => foldText(s.text))
    .sort((a, b) => a.order - b.order)
  const units = blockUnits(block)
  if (!sents.length || !units.length) return out

  let hay = ''
  const cells: HayCell[] = []
  for (const u of units) {
    for (let i = 0; i < u.text.length; i++) {
      const f = foldText(u.text[i] || '')
      for (const ch of f) {
        hay += ch
        cells.push({ key: u.key, orig: i })
      }
    }
  }

  const marked = new Map<string, Map<number, string>>()
  let cursor = 0
  for (const sent of sents) {
    const n = foldText(sent.text)
    if (!n) continue
    let idx = hay.indexOf(n, cursor)
    if (idx < 0) idx = hay.indexOf(n)
    if (idx < 0) continue
    const end = idx + n.length
    for (let i = idx; i < end; i++) {
      const cell = cells[i]
      if (!cell) continue
      let inner = marked.get(cell.key)
      if (!inner) {
        inner = new Map()
        marked.set(cell.key, inner)
      }
      inner.set(cell.orig, sent.id)
    }
    cursor = end
  }

  for (const u of units) {
    const inner = marked.get(u.key)
    if (!inner?.size) continue
    const perChar = fillOrig(u.text.length, inner)
    const ranges = toRanges(perChar)
    const ids: string[] = []
    for (const r of ranges) {
      if (!ids.includes(r.id)) ids.push(r.id)
    }
    out.set(u.key, { ids, ranges })
  }
  return out
}

export function pageUnitAlign(page: PageLayout): Map<string, UnitAlign> {
  const out = new Map<string, UnitAlign>()
  for (const block of page.blocks || []) {
    for (const [k, v] of mapBlock(block)) out.set(k, v)
  }
  return out
}

export function encodeSentRanges(ranges: SentRange[]): string {
  return ranges.map((r) => `${r.id}:${r.start}-${r.end}`).join(',')
}

export function decodeSentRanges(raw: string | undefined): SentRange[] {
  if (!raw) return []
  const out: SentRange[] = []
  for (const part of raw.split(',')) {
    const m = part.match(/^(s_[a-z0-9]+):(\d+)-(\d+)$/i)
    if (!m) continue
    out.push({ id: m[1]!, start: Number(m[2]), end: Number(m[3]) })
  }
  return out
}

export function spanSentenceId(map: Map<string, UnitAlign>, span: TextSpan): string | undefined {
  return map.get(span.id)?.ids[0]
}

export function mathSentenceId(map: Map<string, UnitAlign>, seg: RichSegment): string | undefined {
  if (!seg.bbox) return undefined
  return map.get(mathUnitKey(seg.bbox))?.ids[0]
}

function textNodeOf(el: HTMLElement): Text | null {
  for (const n of el.childNodes) {
    if (n.nodeType === Node.TEXT_NODE && (n.textContent || '').length) return n as Text
  }
  return null
}

export function charOffsetAt(el: HTMLElement, clientX: number): number {
  const tn = textNodeOf(el)
  if (!tn) return 0
  const len = tn.length
  const range = document.createRange()
  let lo = 0
  let hi = len
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    range.setStart(tn, mid)
    range.setEnd(tn, mid)
    if (range.getBoundingClientRect().left <= clientX) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** 一行 span 跨多句时，按鼠标落在哪一段字符上来选 */
export function pickSentenceIdFromTarget(el: HTMLElement, clientX: number): string | null {
  const ranges = decodeSentRanges(el.dataset.sentRanges)
  const off = charOffsetAt(el, clientX)
  if (ranges.length) {
    const hit = ranges.find((r) => off >= r.start && off < r.end) || ranges.find((r) => off <= r.end)
    return hit?.id || ranges[0]?.id || null
  }
  const ids = (el.dataset.sentenceIds || el.dataset.sentenceId || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  return ids[0] || null
}

export function textNodeOfEl(el: HTMLElement): Text | null {
  return textNodeOf(el)
}
