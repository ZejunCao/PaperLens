<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { PageLayout, RichSegment, TextSpan } from '@/types/document'
import { paperAssetUrl } from '@/api/papers'
import KatexView from '@/components/reader/KatexView.vue'
import { normalizeSpacedLatex } from '@/lib/inlineMath'
import { encodeSentRanges, mathUnitKey, pageUnitAlign, pickSentenceIdFromTarget } from '@/lib/sentenceLayout'

const props = defineProps<{
  paperId: string
  page: PageLayout
  scale: number
}>()

const emit = defineEmits<{
  hoverSentence: [id: string | null]
}>()

const width = computed(() => props.page.width * props.scale)
const height = computed(() => props.page.height * props.scale)

const layoutImages = computed(() =>
  (props.page.images || []).filter((img) => img.kind !== 'formula'),
)

const CSS_ASCENDER = 0.72

type LayerItem =
  | { kind: 'text'; id: string; blockId: string; span: TextSpan; y: number; x: number }
  | { kind: 'math'; id: string; mathKey: string; seg: RichSegment; y: number; x: number }

const unitAlign = computed(() => pageUnitAlign(props.page))

function itemSentenceIds(item: LayerItem): string[] {
  if (item.kind === 'text') return unitAlign.value.get(item.span.id)?.ids || []
  return unitAlign.value.get(item.mathKey)?.ids || []
}

function itemSentRanges(item: LayerItem): string {
  const key = item.kind === 'text' ? item.span.id : item.mathKey
  const ranges = unitAlign.value.get(key)?.ranges || []
  return encodeSentRanges(ranges)
}

function onLayoutPointerOver(e: PointerEvent) {
  const el = (e.target as HTMLElement | null)?.closest?.('[data-sentence-id]') as HTMLElement | null
  if (!el) return
  const id = pickSentenceIdFromTarget(el, e.clientX)
  if (id) emit('hoverSentence', id)
}

function onLayoutPointerLeave() {
  emit('hoverSentence', null)
}

const inlineMath = computed(() => {
  const out: RichSegment[] = []
  for (const b of props.page.blocks) {
    for (const seg of b.segments ?? []) {
      if (seg.kind !== 'math' || !seg.bbox || seg.bbox.length < 4) continue
      if (!(seg.latex || '').trim()) continue
      out.push(seg)
    }
  }
  return out
})

const columns = computed(() => {
  const pageW = props.page.width
  const mid = pageW / 2
  let l0 = Infinity
  let l1 = 0
  let r0 = Infinity
  let r1 = 0
  for (const b of props.page.blocks) {
    const [x0, , x1] = b.bbox
    const w = x1 - x0
    // 过宽通栏、公式贴图都不参与双栏聚类，避免单栏论文被拆开、公式盒收成自身宽度
    if (b.type === 'formula') continue
    if (w < 70 || w > pageW * 0.62) continue
    const cx = (x0 + x1) / 2
    if (cx < mid) {
      l0 = Math.min(l0, x0)
      l1 = Math.max(l1, x1)
    } else {
      r0 = Math.min(r0, x0)
      r1 = Math.max(r1, x1)
    }
  }
  const gap = r0 - l1
  if (
    Number.isFinite(l0) &&
    Number.isFinite(r0) &&
    l1 - l0 > 90 &&
    r1 - r0 > 90 &&
    gap > 10 &&
    l1 < pageW * 0.55 &&
    r0 > pageW * 0.45
  ) {
    return { two: true, left: [l0, l1] as const, right: [r0, r1] as const }
  }
  let s0 = Infinity
  let s1 = 0
  for (const b of props.page.blocks) {
    const [x0, , x1] = b.bbox
    const w = x1 - x0
    if (b.type === 'formula' || b.type === 'figure') continue
    if (w < pageW * 0.4 || w > pageW * 0.96) continue
    s0 = Math.min(s0, x0)
    s1 = Math.max(s1, x1)
  }
  if (!Number.isFinite(s0) || s1 - s0 < pageW * 0.35) {
    s0 = pageW * 0.1
    s1 = pageW * 0.9
  }
  return { two: false, left: [s0, s1] as const, right: [s0, s1] as const }
})

function itemColumn(x: number): 0 | 1 {
  const c = columns.value
  if (!c.two) return 0
  const mid = (c.left[1] + c.right[0]) / 2
  return x < mid ? 0 : 1
}

function looksLikeLatex(text: string): boolean {
  return /\\[a-zA-Z]+/.test(text)
}

function spanCoveredByInlineMath(span: TextSpan): boolean {
  if (looksLikeLatex(span.text || '')) return true
  const [x0, y0, x1, y1] = span.bbox
  const area = Math.max(1, (x1 - x0) * (y1 - y0))
  for (const seg of inlineMath.value) {
    if (!seg.bbox) continue
    const b = seg.bbox
    const ix0 = Math.max(x0, b[0])
    const iy0 = Math.max(y0, b[1])
    const ix1 = Math.min(x1, b[2])
    const iy1 = Math.min(y1, b[3])
    if (ix1 <= ix0 || iy1 <= iy0) continue
    if (((ix1 - ix0) * (iy1 - iy0)) / area >= 0.35) return true
  }
  return false
}

function spanWithinBlock(span: TextSpan, blockBbox: number[]): boolean {
  if (!span.bbox || span.bbox.length < 4 || blockBbox.length < 4) return true
  const [bx0, by0, bx1, by1] = blockBbox
  const [sx0, sy0, sx1, sy1] = span.bbox
  const cx = (sx0 + sx1) / 2
  const cy = (sy0 + sy1) / 2
  const tolY = 10
  const tolX = 24
  return cx >= bx0 - tolX && cx <= bx1 + tolX && cy >= by0 - tolY && cy <= by1 + tolY
}

/** 正文 + 行内公式按阅读顺序排进同一 DOM 流，框选才接近所见即所得 */
const readingItems = computed(() => {
  const items: LayerItem[] = []
  for (const block of props.page.blocks) {
    if (block.meta?.layout_skip) continue
    for (const span of block.spans) {
      if (!spanWithinBlock(span, block.bbox)) continue
      if (spanCoveredByInlineMath(span)) continue
      items.push({
        kind: 'text',
        id: span.id,
        blockId: block.id,
        span,
        y: span.bbox[1],
        x: span.bbox[0],
      })
    }
  }
  inlineMath.value.forEach((seg, i) => {
    const b = seg.bbox!
    items.push({
      kind: 'math',
      id: `math-${i}-${b[0]}-${b[1]}`,
      mathKey: mathUnitKey(b),
      seg,
      y: b[1],
      x: b[0],
    })
  })
  items.sort((a, b) => {
    const ca = itemColumn(a.x)
    const cb = itemColumn(b.x)
    if (ca !== cb) return ca - cb
    if (Math.abs(a.y - b.y) > 8) return a.y - b.y
    return a.x - b.x
  })
  return items
})

function spanStyle(span: TextSpan) {
  const x0 = span.bbox[0] ?? 0
  const y0 = span.bbox[1] ?? 0
  const sizePx = Math.max(5.5, span.font_size * props.scale)
  const asc =
    span.ascender && span.ascender > 0 ? Math.min(Math.max(span.ascender, 0.55), 0.95) : 0.8
  let baselineY = y0 + span.font_size * asc
  const y1 = span.bbox[3] ?? y0
  if (
    typeof span.origin_y === 'number' &&
    span.origin_y >= y0 - 1 &&
    span.origin_y <= y1 + span.font_size * 0.35
  ) {
    baselineY = span.origin_y
  }
  const top = baselineY * props.scale - sizePx * CSS_ASCENDER
  const bold = (span.flags & 2 ** 4) !== 0 || /bold|medi|black/i.test(span.font_name || '')
  const italic =
    (span.flags & 2 ** 1) !== 0 || /italic|oblique|CMMI|CMMIB/i.test(span.font_name || '')
  let color = '#1a122e'
  if (typeof span.color === 'number' && span.color > 0) {
    const r = (span.color >> 16) & 255
    const g = (span.color >> 8) & 255
    const b = span.color & 255
    color = `rgb(${r},${g},${b})`
  }
  const boxW = Math.max(1, ((span.bbox[2] ?? x0) - x0) * props.scale)
  return {
    position: 'absolute' as const,
    left: `${x0 * props.scale}px`,
    top: `${top}px`,
    width: `${boxW}px`,
    fontSize: `${sizePx}px`,
    lineHeight: 1,
    fontWeight: bold ? 700 : 400,
    fontStyle: italic ? 'italic' : 'normal',
    color,
    whiteSpace: 'nowrap' as const,
    overflow: 'visible' as const,
    fontFamily: '"Times New Roman", "Liberation Serif", "Noto Serif", Georgia, serif',
  }
}

function fitSpanEl(el: HTMLElement, span: TextSpan) {
  el.style.wordSpacing = '0px'
  el.style.transform = 'none'
  const boxW = Math.max(1, ((span.bbox[2] ?? 0) - (span.bbox[0] ?? 0)) * props.scale)
  const prevWidth = el.style.width
  el.style.width = 'auto'
  const natural = el.scrollWidth
  el.style.width = prevWidth
  if (natural < 1) return
  const extra = boxW - natural
  const spaces = Math.max(0, (el.textContent || '').split(' ').length - 1)
  if (spaces > 0 && extra >= -0.25 * boxW) {
    el.style.wordSpacing = `${extra / spaces}px`
  } else if (extra < -0.02 * boxW) {
    el.style.transform = `scaleX(${boxW / natural})`
    el.style.transformOrigin = 'left top'
  }
}

const spanById = computed(() => {
  const map = new Map<string, TextSpan>()
  for (const block of props.page.blocks) {
    for (const span of block.spans) map.set(span.id, span)
  }
  return map
})

const rootEl = ref<HTMLElement | null>(null)

let inlineFitRaf = 0

watch(
  () => [props.scale, props.page, readingItems.value.length] as const,
  () => {
    nextTick(() => {
      const root = rootEl.value
      if (!root) return
      root.querySelectorAll<HTMLElement>('[data-span-id]').forEach((el) => {
        const span = spanById.value.get(el.dataset.spanId || '')
        if (span) fitSpanEl(el, span)
      })
      scheduleFitInlineMath()
    })
  },
  { immediate: true },
)

function scheduleFitInlineMath() {
  if (inlineFitRaf) cancelAnimationFrame(inlineFitRaf)
  inlineFitRaf = requestAnimationFrame(() => {
    inlineFitRaf = 0
    fitInlineMathBoxes()
  })
}

function columnOverlap(a: DOMRect, b: DOMRect): boolean {
  const ix0 = Math.max(a.left, b.left)
  const ix1 = Math.min(a.right, b.right)
  return ix1 - ix0 > Math.min(a.width, b.width, 24) * 0.18
}

/** 行内公式渲染后：缩放到正文字带内，禁止放大，避免盖住上下行 */
function fitInlineMathBoxes() {
  const root = rootEl.value
  if (!root) return
  const inlines = [...root.querySelectorAll<HTMLElement>('[data-math-inline]')]
  if (!inlines.length) return
  const displays = [...root.querySelectorAll<HTMLElement>('[data-math-display]')]
  const texts = [...root.querySelectorAll<HTMLElement>('[data-span-id]')]
  const keep = 1 * props.scale

  for (const box of inlines) {
    const host = box.querySelector<HTMLElement>('.katex-host')
    const inkEl = box.querySelector<HTMLElement>('.katex')
    const strut = box.querySelector<HTMLElement>('.math-strut')
    if (!host || !inkEl || !strut) continue
    host.style.transform = 'none'

    const fontSize = parseFloat(getComputedStyle(box).fontSize) || 10
    const boxR = box.getBoundingClientRect()
    const ink = inkEl.getBoundingClientRect()
    const baseline = strut.getBoundingClientRect().bottom
    const textTop = baseline - CSS_ASCENDER * fontSize
    const textBottom = baseline + (1 - CSS_ASCENDER) * fontSize

    let prevBaseline = -1e9
    let nextBaseline = 1e9
    for (const el of texts) {
      const r = el.getBoundingClientRect()
      if (!columnOverlap(boxR, r)) continue
      const fs = parseFloat(getComputedStyle(el).fontSize) || fontSize
      const b = r.top + CSS_ASCENDER * fs
      if (b < baseline - fs * 0.35) prevBaseline = Math.max(prevBaseline, b)
      else if (b > baseline + fs * 0.35) nextBaseline = Math.min(nextBaseline, b)
    }

    let opaqueAbove = -1e9
    let opaqueBelow = 1e9
    for (const el of displays) {
      const r = el.getBoundingClientRect()
      if (!columnOverlap(boxR, r)) continue
      if (r.bottom <= baseline) opaqueAbove = Math.max(opaqueAbove, r.bottom)
      else if (r.top >= baseline) opaqueBelow = Math.min(opaqueBelow, r.top)
    }

    const pitch = prevBaseline > -1e8 ? baseline - prevBaseline : fontSize * 1.15
    const lineGap = Math.max(0, pitch - fontSize)
    const maxExtra = Math.max(0, Math.min((lineGap - keep) / 2, fontSize * 0.12))
    const rise = Math.max(0.5, baseline - ink.top)
    const drop = Math.max(0.5, ink.bottom - baseline)
    let s = 1
    const allowTop = textTop - maxExtra
    const allowBottom = textBottom + maxExtra
    s = Math.min(s, (baseline - allowTop) / rise, (allowBottom - baseline) / drop)
    if (opaqueAbove > -1e8) {
      s = Math.min(s, (baseline - opaqueAbove - keep) / rise)
    }
    if (opaqueBelow < 1e8) {
      s = Math.min(s, (opaqueBelow - keep - baseline) / drop)
    }
    if (nextBaseline < 1e8) {
      // 给下一行留出空隙，避免 \mathcal/\sqrt 压住下面文字
      const nextTop = nextBaseline - CSS_ASCENDER * fontSize
      s = Math.min(s, (nextTop - keep - baseline) / drop)
    }
    s = Math.max(0.55, Math.min(s, 1))
    const originY = baseline - host.getBoundingClientRect().top
    host.style.transformOrigin = `left ${originY}px`
    host.style.transform = Math.abs(s - 1) < 0.02 ? 'none' : `scale(${s})`
  }
}

function columnBox(x: number): readonly [number, number] {
  const c = columns.value
  if (!c.two) return c.left
  const mid = (c.left[1] + c.right[0]) / 2
  return x < mid ? c.left : c.right
}

function isDisplayMath(seg: RichSegment): boolean {
  if (seg.display) return true
  const tex = seg.latex || ''
  if (/\\tag\s*\{/.test(tex)) return true
  const b = seg.bbox
  if (!b || b.length < 4) return false
  return b[3] - b[1] > 22
}

function latexIsComplex(tex: string): boolean {
  return /\\frac|\\sum|\\prod|\\int|\\underbrace|\\overline|\\sqrt|\\begin|\\mathbb/.test(tex)
}

function neighborTextBand(seg: RichSegment): {
  prevOrigin: number | null
  nextOrigin: number | null
  displayPrev: number
  displayNext: number
  originY: number | null
  fontSize: number | null
} {
  const b = seg.bbox!
  const cx = (b[0] + b[2]) / 2
  const cy = (b[1] + b[3]) / 2
  let prevOrigin: number | null = null
  let nextOrigin: number | null = null
  let displayPrev = 0
  let displayNext = props.page.height
  let originY: number | null = null
  let fontSize: number | null = null
  let bestSame = 1e9
  for (const block of props.page.blocks) {
    for (const span of block.spans) {
      const sb = span.bbox
      if (!sb || sb.length < 4) continue
      const scx = (sb[0] + sb[2]) / 2
      if (Math.abs(scx - cx) > 160) continue
      const so = typeof span.origin_y === 'number' ? span.origin_y : sb[3]
      const scy = (sb[1] + sb[3]) / 2
      if (scy < cy - 3) {
        prevOrigin = prevOrigin == null ? so : Math.max(prevOrigin, so)
        displayPrev = Math.max(displayPrev, sb[3])
      } else if (scy > cy + 3) {
        nextOrigin = nextOrigin == null ? so : Math.min(nextOrigin, so)
        displayNext = Math.min(displayNext, sb[1])
      } else {
        const d = Math.abs(scy - cy)
        if (d < bestSame) {
          bestSame = d
          originY = so
          fontSize = span.font_size || 10
        }
      }
    }
    for (const other of block.segments ?? []) {
      if (other === seg || other.kind !== 'math' || !other.bbox || other.bbox.length < 4) continue
      if (!isDisplayMath(other)) continue
      const ob = other.bbox
      const ocx = (ob[0] + ob[2]) / 2
      if (Math.abs(ocx - cx) > 180) continue
      if (ob[3] < cy - 2) displayPrev = Math.max(displayPrev, ob[3])
      else if (ob[1] > cy + 2) displayNext = Math.min(displayNext, ob[1])
    }
  }
  return { prevOrigin, nextOrigin, displayPrev, displayNext, originY, fontSize }
}

function mathBox(seg: RichSegment) {
  const b = seg.bbox!
  const display = isDisplayMath(seg)
  const nb = neighborTextBand(seg)
  if (display) {
    const [cx0, cx1] = columnBox((b[0] + b[2]) / 2)
    const keep = 1
    const padTop = Math.min(3, Math.max(0, (b[1] - nb.displayPrev - keep) * 0.45))
    const padBot = Math.min(3, Math.max(0, (nb.displayNext - b[3] - keep) * 0.45))
    return {
      x: cx0,
      y: b[1] - padTop,
      w: Math.max(cx1 - cx0, 40),
      h: Math.max(b[3] - b[1], 14) + padTop + padBot,
      display,
      extraAscent: 0,
    }
  }
  const body = Math.min(Math.max(nb.fontSize || 10, 9), 10.5)
  const baseline = nb.originY ?? b[3]
  const keep = 1
  const pitch = nb.prevOrigin != null ? baseline - nb.prevOrigin : body * 1.15
  const lineGap = Math.max(0, pitch - body)
  let extra = Math.max(0, (lineGap - keep) / 2)
  const textTop = baseline - CSS_ASCENDER * body
  const textBottom = baseline + (1 - CSS_ASCENDER) * body
  extra = Math.min(extra, Math.max(0, textTop - nb.displayPrev - keep))
  extra = Math.min(extra, Math.max(0, nb.displayNext - textBottom - keep))
  // 行内公式只允许少量出头，避免 \mathcal/\sqrt 盖住上下行
  const paintExtra = Math.min(extra, body * 0.12)
  const gapX = inlineMathGapX(seg, body)
  return {
    x: b[0] + gapX,
    y: textTop - paintExtra,
    w: Math.max(b[2] - b[0], 12),
    h: paintExtra + body + paintExtra,
    display: false,
    body,
    extraAscent: paintExtra,
  }
}

function inlineMathGapX(seg: RichSegment, body: number): number {
  const b = seg.bbox!
  const cy = (b[1] + b[3]) / 2
  let prevRight = -1e9
  let prevText = ''
  for (const block of props.page.blocks) {
    for (const span of block.spans) {
      if (spanCoveredByInlineMath(span)) continue
      const sb = span.bbox
      if (!sb || sb.length < 4) continue
      if (Math.abs((sb[1] + sb[3]) / 2 - cy) > 6) continue
      if (sb[2] <= b[0] + 1.8 && sb[2] > prevRight) {
        prevRight = sb[2]
        prevText = span.text || ''
      }
    }
  }
  if (prevRight < 0) return 0
  const t = prevText.trimEnd()
  if (!t) return 0
  const last = t[t.length - 1]
  const tex = (seg.latex || '').trim()
  if ('([{“‘'.includes(last)) return 0
  if (/^[),.;:!?]/.test(tex)) return 0
  const need = body * 0.22
  const gap = b[0] - prevRight
  if (gap >= need - 0.15) return 0
  return Math.max(0, need - Math.max(0, gap))
}

function eqTag(seg: RichSegment): string {
  const m = (seg.latex || '').match(/\\tag\s*\{([^}]+)\}/)
  if (!m) return ''
  const n = m[1].trim()
  if (!n) return ''
  return n.startsWith('(') ? n : `(${n})`
}

function mathBoxStyle(seg: RichSegment) {
  const box = mathBox(seg)
  const sizePx = Math.max(8, (box.display ? 10 : (box.body ?? 10)) * props.scale)
  const extraPx = (box.extraAscent ?? 0) * props.scale
  return {
    position: 'absolute' as const,
    left: `${box.x * props.scale}px`,
    top: `${box.y * props.scale}px`,
    width: `${box.w * props.scale}px`,
    height: `${box.h * props.scale}px`,
    paddingTop: extraPx ? `${extraPx}px` : undefined,
    fontSize: `${sizePx}px`,
    lineHeight: 1,
    whiteSpace: (box.display ? 'normal' : 'nowrap') as 'normal' | 'nowrap',
    display: box.display ? ('flex' as const) : undefined,
    justifyContent: box.display ? ('center' as const) : undefined,
    alignItems: box.display ? ('center' as const) : undefined,
    color: '#1a122e',
    overflow: 'visible' as const,
    userSelect: 'text' as const,
  }
}

function eqNumStyle(seg: RichSegment) {
  const sizePx = Math.max(8, 10 * props.scale)
  return {
    position: 'absolute' as const,
    right: '0px',
    top: '50%',
    transform: 'translateY(-50%)',
    fontSize: `${sizePx}px`,
    lineHeight: 1,
    fontFamily: '"Times New Roman", "Liberation Serif", "Noto Serif", Georgia, serif',
    color: '#1a122e',
    userSelect: 'text' as const,
    pointerEvents: 'auto' as const,
    zIndex: 2,
  }
}

function displayMathImgStyle(seg: RichSegment) {
  const tag = eqTag(seg)
  return {
    display: 'block',
    height: '100%',
    width: 'auto',
    maxHeight: '100%',
    maxWidth: tag ? 'calc(100% - 2.4em)' : '100%',
    objectFit: 'contain' as const,
    flex: '0 1 auto',
  }
}

function displayMathLatex(seg: RichSegment): string {
  return normalizeSpacedLatex((seg.latex || seg.text || '').replace(/\\tag\s*\{[^}]*\}/g, '').trim())
}

function mathFitWidth(seg: RichSegment): number {
  return mathBox(seg).w * props.scale
}

function mathFitHeight(seg: RichSegment): number {
  return mathBox(seg).h * props.scale
}

function imageStyle(bbox: number[]) {
  const x0 = bbox[0] ?? 0
  const y0 = bbox[1] ?? 0
  const x1 = bbox[2] ?? x0
  const y1 = bbox[3] ?? y0
  return {
    position: 'absolute' as const,
    left: `${x0 * props.scale}px`,
    top: `${y0 * props.scale}px`,
    width: `${Math.max(1, (x1 - x0) * props.scale)}px`,
    height: `${Math.max(1, (y1 - y0) * props.scale)}px`,
    objectFit: 'contain' as const,
  }
}

type SelAnchor = { el: HTMLElement; offset: number; atomic: boolean; index: number }

let selecting = false
let selStart: SelAnchor | null = null

function selNodes(): HTMLElement[] {
  const root = rootEl.value
  if (!root) return []
  return [...root.querySelectorAll<HTMLElement>('[data-sel]')]
}

function textNodeOf(el: HTMLElement): Text | null {
  for (const n of el.childNodes) {
    if (n.nodeType === Node.TEXT_NODE && (n.textContent || '').length) return n as Text
  }
  return null
}

function charOffset(el: HTMLElement, clientX: number): number {
  const tn = textNodeOf(el)
  if (!tn) return 0
  const len = (tn.textContent || '').length
  const range = document.createRange()
  let lo = 0
  let hi = len
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    range.setStart(tn, mid)
    range.setEnd(tn, mid)
    const left = range.getBoundingClientRect().left
    if (left <= clientX) lo = mid + 1
    else hi = mid
  }
  return lo
}

function hitAnchor(clientX: number, clientY: number): SelAnchor | null {
  const root = rootEl.value
  if (!root) return null
  const r0 = root.getBoundingClientRect()
  const x = (clientX - r0.left) / props.scale
  const y = (clientY - r0.top) / props.scale
  const col = itemColumn(x)
  const nodes = selNodes().filter((el) => Number(el.dataset.selCol) === col)
  if (!nodes.length) return null

  const boxes = nodes.map((el) => {
    const r = el.getBoundingClientRect()
    return {
      el,
      y0: (r.top - r0.top) / props.scale,
      y1: (r.bottom - r0.top) / props.scale,
      x0: (r.left - r0.left) / props.scale,
      x1: (r.right - r0.left) / props.scale,
      index: Number(el.dataset.selIndex),
    }
  })

  let line = boxes.filter((b) => y >= b.y0 - 3 && y <= b.y1 + 3)
  if (!line.length) {
    let best = boxes[0]
    let bestD = 1e9
    for (const b of boxes) {
      const d = y < b.y0 ? b.y0 - y : y > b.y1 ? y - b.y1 : 0
      if (d < bestD || (d === bestD && b.y0 < best.y0)) {
        bestD = d
        best = b
      }
    }
    const band = (best.y0 + best.y1) / 2
    line = boxes.filter((b) => Math.abs((b.y0 + b.y1) / 2 - band) < 6)
  }
  line.sort((a, b) => a.x0 - b.x0)
  const first = line[0]
  const last = line[line.length - 1]
  let hit = first
  if (x >= last.x1 - 0.4) hit = last
  else if (x > first.x0) {
    for (const b of line) {
      if (b.x0 <= x) hit = b
    }
  }

  const atomic = hit.el.hasAttribute('data-sel-atomic')
  let offset = 0
  if (atomic) offset = x >= (hit.x0 + hit.x1) / 2 ? 1 : 0
  else if (x <= hit.x0) offset = 0
  else if (x >= hit.x1) offset = (textNodeOf(hit.el)?.textContent || '').length
  else offset = charOffset(hit.el, clientX)

  return { el: hit.el, offset, atomic, index: hit.index }
}

function compareAnchor(a: SelAnchor, b: SelAnchor): number {
  if (a.index !== b.index) return a.index - b.index
  return a.offset - b.offset
}

function applySelRange(a: SelAnchor, b: SelAnchor) {
  const [from, to] = compareAnchor(a, b) <= 0 ? [a, b] : [b, a]
  const range = document.createRange()
  if (from.atomic) range.setStart(from.el, from.offset > 0 ? from.el.childNodes.length : 0)
  else {
    const tn = textNodeOf(from.el)
    if (!tn) range.setStart(from.el, 0)
    else range.setStart(tn, Math.min(from.offset, tn.length))
  }
  if (to.atomic) range.setEnd(to.el, to.offset > 0 ? to.el.childNodes.length : 0)
  else {
    const tn = textNodeOf(to.el)
    if (!tn) range.setEnd(to.el, to.el.childNodes.length)
    else range.setEnd(tn, Math.min(to.offset, tn.length))
  }
  const sel = window.getSelection()
  if (!sel) return
  sel.removeAllRanges()
  sel.addRange(range)
}

function onSelDown(e: PointerEvent) {
  if (e.button !== 0) return
  const hit = hitAnchor(e.clientX, e.clientY)
  if (!hit) return
  if (e.shiftKey && selStart) {
    e.preventDefault()
    applySelRange(selStart, hit)
    return
  }
  e.preventDefault()
  selecting = true
  selStart = hit
  applySelRange(hit, hit)
  rootEl.value?.setPointerCapture(e.pointerId)
}

function onSelMove(e: PointerEvent) {
  if (!selecting || !selStart) return
  const hit = hitAnchor(e.clientX, e.clientY)
  if (!hit) return
  applySelRange(selStart, hit)
}

function onSelUp(e: PointerEvent) {
  if (!selecting) return
  selecting = false
  try {
    rootEl.value?.releasePointerCapture(e.pointerId)
  } catch {
    /* already released */
  }
}

function onSelCopy(e: ClipboardEvent) {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !rootEl.value) return
  const nodes = selNodes()
  const bits: string[] = []
  let prev: HTMLElement | null = null
  for (const el of nodes) {
    if (!sel.containsNode(el, true)) continue
    if (prev) {
      const pc = Number(prev.dataset.selCol)
      const cc = Number(el.dataset.selCol)
      const py = prev.getBoundingClientRect().top
      const cy = el.getBoundingClientRect().top
      if (pc !== cc) bits.push('\n\n')
      else if (Math.abs(cy - py) > 8) bits.push('\n')
      else bits.push(' ')
    }
    bits.push((el.innerText || el.getAttribute('title') || '').trim())
    prev = el
  }
  const text = bits.join('').replace(/[ \t]+\n/g, '\n').replace(/\n[ \t]+/g, '\n')
  if (!text.trim()) return
  e.preventDefault()
  e.clipboardData?.setData('text/plain', text)
}

onMounted(() => {
  const root = rootEl.value
  if (!root) return
  root.addEventListener('pointerdown', onSelDown)
  root.addEventListener('pointermove', onSelMove)
  root.addEventListener('pointerup', onSelUp)
  root.addEventListener('pointercancel', onSelUp)
  root.addEventListener('copy', onSelCopy)
})

onBeforeUnmount(() => {
  const root = rootEl.value
  if (!root) return
  root.removeEventListener('pointerdown', onSelDown)
  root.removeEventListener('pointermove', onSelMove)
  root.removeEventListener('pointerup', onSelUp)
  root.removeEventListener('pointercancel', onSelUp)
  root.removeEventListener('copy', onSelCopy)
})
</script>

<template>
  <div
    ref="rootEl"
    data-layout-root
    class="relative bg-white shadow-sm ring-1 ring-black/5"
    :style="{ width: `${width}px`, height: `${height}px` }"
    @pointerover="onLayoutPointerOver"
    @pointerleave="onLayoutPointerLeave"
  >
    <img
      v-for="img in layoutImages"
      :key="img.id"
      :src="paperAssetUrl(paperId, img.path)"
      alt=""
      :style="imageStyle(img.bbox)"
      class="pointer-events-none absolute z-0 select-none"
      draggable="false"
    />

    <template v-for="(item, idx) in readingItems" :key="item.id">
      <div
        v-if="item.kind === 'math' && isDisplayMath(item.seg)"
        class="absolute z-[1] select-text overflow-visible"
        data-sel
        data-sel-atomic
        data-math-display=""
        :data-sentence-id="itemSentenceIds(item)[0] || undefined"
        :data-sentence-ids="itemSentenceIds(item).join(',') || undefined"
        :data-sent-ranges="itemSentRanges(item) || undefined"
        :data-sel-index="idx"
        :data-sel-col="itemColumn(item.x)"
        :style="mathBoxStyle(item.seg)"
        :title="item.seg.latex || ''"
      >
        <img
          v-if="item.seg.image_path"
          :src="paperAssetUrl(paperId, item.seg.image_path)"
          alt=""
          :style="displayMathImgStyle(item.seg)"
          class="pointer-events-none select-none"
          draggable="false"
        />
        <KatexView
          v-else
          :latex="displayMathLatex(item.seg)"
          :display="true"
          :title="item.seg.latex || ''"
          :fit-width="mathFitWidth(item.seg)"
          :fit-height="mathFitHeight(item.seg)"
        />
        <span v-if="eqTag(item.seg)" :style="eqNumStyle(item.seg)">{{ eqTag(item.seg) }}</span>
      </div>
      <div
        v-else-if="item.kind === 'math'"
        class="absolute z-[3] select-text overflow-visible math-inline-box"
        data-sel
        data-sel-atomic
        data-math-inline=""
        :data-sentence-id="itemSentenceIds(item)[0] || undefined"
        :data-sentence-ids="itemSentenceIds(item).join(',') || undefined"
        :data-sent-ranges="itemSentRanges(item) || undefined"
        :data-sel-index="idx"
        :data-sel-col="itemColumn(item.x)"
        :data-math-complex="latexIsComplex(item.seg.latex || '') ? '1' : '0'"
        :style="mathBoxStyle(item.seg)"
        :title="item.seg.latex || ''"
      >
        <span class="math-strut" aria-hidden="true" />
        <KatexView
          class="layout-inline"
          :latex="normalizeSpacedLatex(item.seg.latex || item.seg.text || '')"
          :display="false"
          :title="item.seg.latex || ''"
          @painted="scheduleFitInlineMath"
        />
      </div>
      <span
        v-else
        :data-block-id="item.blockId"
        :data-span-id="item.id"
        :data-sentence-id="itemSentenceIds(item)[0] || undefined"
        :data-sentence-ids="itemSentenceIds(item).join(',') || undefined"
        :data-sent-ranges="itemSentRanges(item) || undefined"
        data-sel
        :data-sel-index="idx"
        :data-sel-col="itemColumn(item.x)"
        class="absolute z-[1] select-text"
        :style="spanStyle(item.span)"
        >{{ item.span.text }}</span
      >
    </template>
  </div>
</template>

<style scoped>
.math-strut {
  display: inline-block;
  width: 0;
  height: 0.72em;
  vertical-align: baseline;
}
.math-inline-box :deep(.katex-host) {
  vertical-align: baseline;
  font-size: 1em;
  max-width: none;
}
.sentence-hit {
  background-color: rgb(253 224 71 / 0.42);
  box-shadow: 0 0 0 2px rgb(245 158 11 / 0.28);
  border-radius: 2px;
}
</style>
