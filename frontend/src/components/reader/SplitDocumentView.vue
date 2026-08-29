<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-vue-next'
import WheelGestures, { type WheelEventState } from 'wheel-gestures'
import LayoutPage from '@/components/reader/LayoutPage.vue'
import KatexView from '@/components/reader/KatexView.vue'
import { fetchDocument, fetchPaper, paperAssetUrl, retryParse } from '@/api/papers'
import { fetchTranslations, translatePaperPage } from '@/api/settings'
import type { ContentBlock, DocumentModel, Sentence } from '@/types/document'
import type { PageTranslation } from '@/types/translation'
import type { Paper } from '@/types'
import { STATUS_LABEL, parseStageLabel } from '@/types'
import { splitInlineMath, type RichChunk } from '@/lib/inlineMath'
import { decodeSentRanges, textNodeOfEl } from '@/lib/sentenceLayout'

const props = withDefaults(
  defineProps<{
    paperId: string
    pdfScale?: number
    fontScale?: number
    splitPercent?: number
  }>(),
  {
    pdfScale: 1,
    fontScale: 1,
    splitPercent: 50,
  },
)

const emit = defineEmits<{
  'update:page': [page: number]
  'page-count': [count: number]
  'paper-update': [paper: Paper]
  'update:fit-scale': [scale: number]
}>()

const PAGE_GAP = 12
const LEFT_PAD = 4
const scrollRef = ref<HTMLDivElement | null>(null)
const fitScale = ref(1)
const paper = ref<Paper | null>(null)
const documentModel = ref<DocumentModel | null>(null)
const loading = ref(true)
const error = ref('')
const retrying = ref(false)
const currentPage = ref(1)
const llmConfigured = ref(false)
const translationPages = ref<Record<string, PageTranslation>>({})
const translatingPage = ref<number | null>(null)
const pinnedSentence = ref<{ id: string; page: number; blockId: string; fallback: string } | null>(null)
let hoverClearTimer: ReturnType<typeof setTimeout> | null = null
let hoveredSentenceId: string | null = null

let pollTimer: ReturnType<typeof setInterval> | null = null
let dwellTimer: ReturnType<typeof setTimeout> | null = null
let translateAbort: AbortController | null = null
let scrollRaf = 0
let resizeObserver: ResizeObserver | null = null
const spacePressed = ref(false)
const panning = ref(false)
let panPointerId: number | null = null
let panStartX = 0
let panStartY = 0
let panScrollLeft = 0
let panScrollTop = 0
let wheelAbort: AbortController | null = null
/** 各页右栏页内位移（不用 overflow:auto，避免浏览器把滚轮锁死在已到底的容器上）。 */
const rightOffsets = ref<Record<number, number>>({})
type WheelOwner = 'inner' | 'outer'
let activeSlide: {
  owner: WheelOwner
  direction: -1 | 1
} | null = null
/** https://github.com/xiel/wheel-gestures — 区分用户新滑 vs 惯性衰减 */
let wheelGestures: ReturnType<typeof WheelGestures> | null = null
let pendingWheelPane: HTMLElement | null = null
/** 页内撞底后，事件流停住多久才解锁，允许下一次滑动重判（只用于解锁，不用于把惯性接到全文） */
const BOUNDARY_IDLE_MS = 120
let boundaryIdleTimer: ReturnType<typeof setTimeout> | null = null
/** 控制台执行 localStorage.setItem('paperlens:wheel-debug', '1') 后刷新，可看意图分类 */
const WHEEL_DEBUG =
  typeof localStorage !== 'undefined' && localStorage.getItem('paperlens:wheel-debug') === '1'

const leftPct = computed(() => Math.min(80, Math.max(20, props.splitPercent)))
const fontPx = computed(() => Math.round(14 * props.fontScale))
const pages = computed(() => documentModel.value?.pages ?? [])
/** 相对「铺满左栏」的缩放：1 = 页宽占满左侧可用宽度 */
const renderScale = computed(() => Math.max(0.2, fitScale.value * props.pdfScale))
const isParsing = computed(
  () => !!paper.value && ['queued', 'parsing'].includes(paper.value.status),
)
const needsParse = computed(
  () => !!paper.value && (paper.value.status === 'uploaded' || paper.value.status === 'failed'),
)
const parseProgressPct = computed(() => {
  const p = paper.value?.parse_progress
  if (typeof p === 'number' && p >= 0) return Math.min(100, Math.max(0, p))
  if (paper.value?.status === 'queued') return 2
  if (paper.value?.status === 'parsing') return 12
  return 0
})
const parseProgressHint = computed(() => {
  const stage = parseStageLabel(paper.value?.parse_stage)
  if (stage) return stage
  if (paper.value?.status === 'queued') return '排队等待'
  if (isParsing.value) return '正在结构化解析'
  return ''
})

function updateFitScale() {
  const el = scrollRef.value
  const pageW = pages.value[0]?.width
  if (!el || !pageW || pageW <= 0) return
  const leftWidth = (el.clientWidth * leftPct.value) / 100
  const avail = Math.max(40, leftWidth - LEFT_PAD * 2)
  const next = avail / pageW
  if (Math.abs(next - fitScale.value) > 0.001) {
    fitScale.value = next
    emit('update:fit-scale', next)
  }
}

function leftPaneEls(): HTMLElement[] {
  const root = scrollRef.value
  if (!root) return []
  return [...root.querySelectorAll<HTMLElement>('[data-left-pane]')]
}

function syncLeftScroll(from?: HTMLElement) {
  const x = from?.scrollLeft ?? leftPaneEls()[0]?.scrollLeft ?? 0
  for (const pane of leftPaneEls()) {
    if (pane !== from) pane.scrollLeft = x
  }
}

async function refreshPaper() {
  paper.value = await fetchPaper(props.paperId)
  emit('paper-update', paper.value)
  if (paper.value.page_count) emit('page-count', paper.value.page_count)
}

async function loadDocumentIfReady() {
  if (!paper.value || paper.value.status !== 'ready') {
    documentModel.value = null
    return
  }
  documentModel.value = await fetchDocument(props.paperId)
  emit('page-count', documentModel.value.page_count)
  await nextTick()
  updateFitScale()
  if (resizeObserver && scrollRef.value) {
    resizeObserver.observe(scrollRef.value)
  }
  updateCurrentPageFromScroll()
  void loadTranslations().then(() => scheduleTranslate(currentPage.value))
}

async function bootstrap() {
  loading.value = true
  error.value = ''
  try {
    await refreshPaper()
    await loadDocumentIfReady()
    // Milestone 0 遗留的 uploaded：自动入队解析
    if (paper.value?.status === 'uploaded') {
      await retryParse(props.paperId)
      await refreshPaper()
      startPolling()
    } else if (isParsing.value) {
      startPolling()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function onRetry() {
  retrying.value = true
  error.value = ''
  try {
    await retryParse(props.paperId)
    await refreshPaper()
    documentModel.value = null
    translationPages.value = {}
    startPolling()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    retrying.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      await refreshPaper()
      if (paper.value?.status === 'ready') {
        await loadDocumentIfReady()
        stopPolling()
      } else if (paper.value?.status === 'failed') {
        stopPolling()
      }
    } catch {
      /* ignore transient */
    }
  }, 1200)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function updateCurrentPageFromScroll() {
  const el = scrollRef.value
  if (!el || !pages.value.length) return
  const mid = el.scrollTop + el.clientHeight * 0.28
  let acc = 0
  let page = 1
  for (let i = 0; i < pages.value.length; i++) {
    const h = (pages.value[i]?.height ?? 0) * renderScale.value + PAGE_GAP
    if (mid < acc + h) {
      page = i + 1
      break
    }
    acc += h
    page = i + 1
  }
  emit('update:page', page)
  if (currentPage.value !== page) {
    currentPage.value = page
    scheduleTranslate(page)
  }
}

function onScroll() {
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  scrollRaf = requestAnimationFrame(updateCurrentPageFromScroll)
}

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  const tag = el?.tagName
  return !!el && (tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable)
}

function onWindowKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && pinnedSentence.value) {
    clearPinnedSentence()
    return
  }
  if (e.code !== 'Space' || isTypingTarget(e.target) || e.repeat) return
  e.preventDefault()
  spacePressed.value = true
}

function onWindowKeyup(e: KeyboardEvent) {
  if (e.code !== 'Space') return
  spacePressed.value = false
  stopPan()
}

function startPan(e: PointerEvent) {
  const pane = (e.currentTarget as HTMLElement | null)?.closest?.('[data-left-pane]') as HTMLElement | null
  const outer = scrollRef.value
  if (!pane || !outer || !spacePressed.value || e.button !== 0) return
  e.preventDefault()
  e.stopPropagation()
  panning.value = true
  panPointerId = e.pointerId
  panStartX = e.clientX
  panStartY = e.clientY
  panScrollLeft = pane.scrollLeft
  panScrollTop = outer.scrollTop
  pane.setPointerCapture(e.pointerId)
}

function movePan(e: PointerEvent) {
  const pane = e.currentTarget as HTMLElement | null
  const outer = scrollRef.value
  if (!pane || !outer || !panning.value || panPointerId !== e.pointerId) return
  e.preventDefault()
  pane.scrollLeft = panScrollLeft - (e.clientX - panStartX)
  syncLeftScroll(pane)
  outer.scrollTop = panScrollTop - (e.clientY - panStartY)
}

function stopPan(e?: PointerEvent) {
  const pane = e?.currentTarget as HTMLElement | undefined
  if (pane && e && panPointerId === e.pointerId && pane.hasPointerCapture?.(e.pointerId)) {
    pane.releasePointerCapture(e.pointerId)
  }
  panning.value = false
  panPointerId = null
}

function onLeftPaneScroll(e: Event) {
  syncLeftScroll(e.currentTarget as HTMLElement)
}

function wheelDeltaY(e: Pick<WheelEvent, 'deltaY' | 'deltaMode'>): number {
  if (e.deltaMode === WheelEvent.DOM_DELTA_LINE) return e.deltaY * 16
  if (e.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    return e.deltaY * (scrollRef.value?.clientHeight ?? 400)
  }
  return e.deltaY
}

function createWheelGestures() {
  // preventWheelAction:false → 我们自己 preventDefault
  // reverseSign:false → 保留浏览器原始 delta 符号，避免和 scrollTop 方向拧反
  const wg = WheelGestures({
    preventWheelAction: false,
    reverseSign: false,
  })
  wg.on('wheel', onWheelGesture)
  return wg
}

function bindOuterWheel(el: HTMLDivElement | null, _prev?: HTMLDivElement | null) {
  wheelAbort?.abort()
  wheelAbort = null
  clearBoundaryIdleUnlock()
  wheelGestures?.disconnect()
  wheelGestures = null
  activeSlide = null
  pendingWheelPane = null
  if (!el) return
  wheelGestures = createWheelGestures()
  wheelAbort = new AbortController()
  window.addEventListener('wheel', onRightPaneWheel, {
    capture: true,
    passive: false,
    signal: wheelAbort.signal,
  })
}

function rightPanePageNo(pane: HTMLElement): number {
  return Number(pane.closest('[data-page]')?.getAttribute('data-page') || 0)
}

function rightContentMax(pane: HTMLElement): number {
  const content = pane.querySelector<HTMLElement>('[data-right-content]')
  if (!content) return 0
  return Math.max(0, content.offsetHeight - pane.clientHeight)
}

function rightOffsetOf(pageNo: number): number {
  return rightOffsets.value[pageNo] ?? 0
}

function setRightOffset(pageNo: number, next: number) {
  if (rightOffsetOf(pageNo) === next) return
  rightOffsets.value = { ...rightOffsets.value, [pageNo]: next }
}

function canInnerScroll(pane: HTMLElement, dy: number): boolean {
  const max = rightContentMax(pane)
  if (max <= 1) return false
  const top = rightOffsetOf(rightPanePageNo(pane))
  if (dy > 0) return top < max - 1
  return top > 1
}

function applyInnerScroll(pane: HTMLElement, dy: number): boolean {
  const pageNo = rightPanePageNo(pane)
  const max = rightContentMax(pane)
  const top = rightOffsetOf(pageNo)
  const next = Math.min(max, Math.max(0, top + dy))
  if (next === top) return false
  setRightOffset(pageNo, next)
  return true
}

function resolveRightPane(e: WheelEvent, outer: HTMLElement): HTMLElement | null {
  const fromTarget = (e.target as HTMLElement | null)?.closest?.('[data-right-pane]') as HTMLElement | null
  if (fromTarget && outer.contains(fromTarget)) return fromTarget
  const hovered = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null
  const fromPoint = hovered?.closest?.('[data-right-pane]') as HTMLElement | null
  if (fromPoint && outer.contains(fromPoint)) return fromPoint
  for (const el of outer.querySelectorAll<HTMLElement>('[data-right-pane]')) {
    const r = el.getBoundingClientRect()
    if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
      return el
    }
  }
  return null
}

function rightThumbStyle(pageNo: number, paneHeight: number) {
  const pane = scrollRef.value?.querySelector(`[data-page="${pageNo}"] [data-right-pane]`) as HTMLElement | null
  const max = pane ? rightContentMax(pane) : 0
  if (max <= 1 || paneHeight <= 0) return { display: 'none' }
  const view = pane?.clientHeight || paneHeight
  const thumb = Math.max(24, (view / (view + max)) * paneHeight)
  const top = (rightOffsetOf(pageNo) / max) * (paneHeight - thumb)
  return {
    height: `${thumb}px`,
    transform: `translateY(${top}px)`,
  }
}

/**
 * 右栏页内滚 + 全文翻页：
 * - 新手势开始时看能不能页内滚，整次手势锁死 owner
 * - owner=inner 且已到底：只吞事件，惯性绝不能连到全文
 * - 到底后再无 wheel 一小段：解锁，下一次滑重新判定（可全文）
 * 惯性/新手势识别用 wheel-gestures（isStart / isEnding）。
 */
function onRightPaneWheel(e: WheelEvent) {
  const outer = scrollRef.value
  const pane = outer ? resolveRightPane(e, outer) : null
  if (!outer || !pane || e.deltaY === 0) return

  e.preventDefault()
  e.stopPropagation()
  pendingWheelPane = pane
  wheelGestures?.feedWheel(e)
}

function clearBoundaryIdleUnlock() {
  if (boundaryIdleTimer != null) {
    clearTimeout(boundaryIdleTimer)
    boundaryIdleTimer = null
  }
}

/** 页内撞底并吞掉惯性后，等事件流真正停住再解锁，避免慢拖尾包被当成「还能继续同一串」。 */
function armBoundaryIdleUnlock() {
  clearBoundaryIdleUnlock()
  boundaryIdleTimer = setTimeout(() => {
    boundaryIdleTimer = null
    activeSlide = null
    wheelGestures?.disconnect()
    wheelGestures = createWheelGestures()
  }, BOUNDARY_IDLE_MS)
}

function onWheelGesture(state: WheelEventState) {
  if (state.isEnding) {
    clearBoundaryIdleUnlock()
    activeSlide = null
    return
  }

  const outer = scrollRef.value
  const pane = pendingWheelPane
  if (!outer || !pane) return

  const dy = wheelDeltaY(state.event)
  if (dy === 0) return
  const direction: -1 | 1 = dy < 0 ? -1 : 1
  const directionChanged = !!activeSlide && activeSlide.direction !== direction
  const canInner = canInnerScroll(pane, dy)

  // 仅新手势 / 换向时重判；同一次手势中途绝不改 owner（防止惯性连全文）
  if (state.isStart || directionChanged || !activeSlide) {
    activeSlide = {
      owner: canInner ? 'inner' : 'outer',
      direction,
    }
  }

  if (WHEEL_DEBUG) {
    console.log('[wheel-debug]', {
      isStart: state.isStart,
      isMomentum: state.isMomentum,
      canInner,
      owner: activeSlide.owner,
      dy: +dy.toFixed(1),
      action:
        activeSlide.owner === 'inner' ? (canInner ? 'inner' : 'swallow') : 'outer',
    })
  }

  if (activeSlide.owner === 'inner') {
    if (canInner) {
      clearBoundaryIdleUnlock()
      applyInnerScroll(pane, dy)
    } else {
      // 已到底：吞掉本串剩余事件（含惯性），绝不 outer.scrollTop
      armBoundaryIdleUnlock()
    }
    return
  }

  clearBoundaryIdleUnlock()
  outer.scrollTop += dy
}

function pageScrollTop(page: number): number {
  const target = Math.min(Math.max(1, page), pages.value.length)
  let top = 0
  for (let i = 0; i < target - 1; i++) {
    top += (pages.value[i]?.height ?? 0) * renderScale.value + PAGE_GAP
  }
  return top
}

function scrollToPage(page: number) {
  const el = scrollRef.value
  if (!el || !pages.value.length) return
  const target = Math.min(Math.max(1, page), pages.value.length)
  const top = pageScrollTop(target)
  el.scrollTo({ top, behavior: 'auto' })
  emit('update:page', target)
  currentPage.value = target
  scheduleTranslate(target)
}

async function loadTranslations() {
  try {
    const data = await fetchTranslations(props.paperId)
    llmConfigured.value = data.configured
    translationPages.value = data.pages || {}
  } catch {
    llmConfigured.value = false
  }
}

function stopTranslate() {
  if (dwellTimer) {
    clearTimeout(dwellTimer)
    dwellTimer = null
  }
  translateAbort?.abort()
  translateAbort = null
}

function scheduleTranslate(page: number) {
  stopTranslate()
  const key = String(page)
  const cached = translationPages.value[key]
  // 重解析后句 ID 会变：旧译文仍标 ready 时强制重译
  if (cached?.status === 'ready' && translationMatchesPage(page, cached)) return
  if (!llmConfigured.value) return
  dwellTimer = setTimeout(() => {
    void runTranslate(page)
  }, 1000)
}

function translationMatchesPage(
  page: number,
  cached: { sentences?: Record<string, string> } | undefined,
): boolean {
  const trIds = Object.keys(cached?.sentences || {})
  if (!trIds.length) return true
  const pageLayout = pages.value.find((p) => p.page === page)
  if (!pageLayout) return true
  const docIds = new Set(
    pageLayout.blocks.flatMap((b) => (b.sentences || []).map((s) => s.id)),
  )
  if (!docIds.size) return true
  return trIds.some((id) => docIds.has(id))
}

async function runTranslate(page: number) {
  const key = String(page)
  if (
    translationPages.value[key]?.status === 'ready' &&
    translationMatchesPage(page, translationPages.value[key])
  ) {
    return
  }
  translatingPage.value = page
  translateAbort = new AbortController()
  try {
    const data = await translatePaperPage(props.paperId, page, translateAbort.signal)
    llmConfigured.value = data.configured
    translationPages.value = data.pages || {}
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return
    const msg = e instanceof Error ? e.message : String(e)
    if (msg.includes('尚未配置')) {
      llmConfigured.value = false
      return
    }
    const pagesMap = { ...translationPages.value }
    pagesMap[key] = {
      status: 'failed',
      error: msg,
      sentences: pagesMap[key]?.sentences || {},
    }
    translationPages.value = pagesMap
  } finally {
    if (translatingPage.value === page) translatingPage.value = null
  }
}

function sentenceText(sent: Sentence): string {
  return sent.full_text?.trim() || sent.text
}

function pageSentences(pageNo: number, block: ContentBlock): Sentence[] {
  return [...(block.sentences || [])]
    .filter((sent) => sent.owner_page == null || sent.owner_page === pageNo)
    .sort((a, b) => a.order - b.order)
}

function sentenceView(pageNo: number, sent: Sentence): { text: string; pending: boolean } {
  const zh = translationPages.value[String(pageNo)]?.sentences?.[sent.id]
  if (zh) return { text: zh, pending: false }
  const pending =
    translatingPage.value === pageNo || translationPages.value[String(pageNo)]?.status === 'pending'
  return { text: sentenceText(sent), pending }
}

function blockSentenceParts(pageNo: number, block: ContentBlock) {
  const parts = pageSentences(pageNo, block).map((sent) => sentenceView(pageNo, sent))
  return {
    parts,
    pending: parts.some((p) => p.pending),
  }
}

function blockDisplay(pageNo: number, block: ContentBlock): { text: string; pending: boolean } {
  const { parts, pending } = blockSentenceParts(pageNo, block)
  if (!parts.length) return { text: block.source_text || '', pending: false }
  let text = ''
  for (let i = 0; i < parts.length; i++) {
    if (i) text += joinGap(parts[i - 1]!.text, parts[i]!.text)
    text += parts[i]!.text
  }
  return { text, pending }
}

function blockRichChunks(pageNo: number, block: ContentBlock): RichChunk[] {
  const segs = block.segments || []
  const hasMathSeg = segs.some((s) => s.kind === 'math' && (s.latex || '').trim())
  const visibleSentences = pageSentences(pageNo, block)
  const hasZh = visibleSentences.some(
    (s) => !!translationPages.value[String(pageNo)]?.sentences?.[s.id],
  )
  if (!hasZh && hasMathSeg) {
    return segs
      .map((seg) => {
        if (seg.kind === 'math' && (seg.latex || '').trim()) {
          return { kind: 'math' as const, text: seg.latex || '', display: !!seg.display }
        }
        const t = (seg.text || '').trim() ? seg.text || '' : ''
        return t ? { kind: 'text' as const, text: t } : null
      })
      .filter((c): c is RichChunk => !!c)
  }
  const raw =
    visibleSentences.length > 0
      ? blockDisplay(pageNo, block).text
      : block.source_text || segs.map((s) => s.text || s.latex || '').join('')
  return splitInlineMath(raw)
}

function applySentenceHover(id: string | null) {
  if (id === hoveredSentenceId) return
  const root = scrollRef.value
  if (root) {
    root.querySelectorAll('.sentence-hit').forEach((el) => el.classList.remove('sentence-hit'))
    root.querySelectorAll('.sentence-hit-ov').forEach((el) => el.remove())
  }
  hoveredSentenceId = id
  if (!id || !root) return
  root.querySelectorAll('[data-sentence-id]').forEach((node) => {
    const el = node as HTMLElement
    const ranges = decodeSentRanges(el.dataset.sentRanges).filter((r) => r.id === id)
    const ids = `${el.dataset.sentenceIds || ''},${el.dataset.sentenceId || ''}`
    if (!ranges.length && !ids.split(',').includes(id)) return
    const tn = textNodeOfEl(el)
    const textLen = (tn?.length ?? el.textContent?.length ?? 0)
    const partial =
      ranges.length > 0 && ranges.some((r) => r.start > 0 || r.end < textLen)
    if (tn && partial) {
      paintSentenceOverlays(el, ranges)
      return
    }
    el.classList.add('sentence-hit')
  })
}

function paintSentenceOverlays(el: HTMLElement, ranges: { start: number; end: number }[]) {
  const tn = textNodeOfEl(el)
  const host = el.closest('[data-layout-root]') as HTMLElement | null
  if (!tn || !host) {
    el.classList.add('sentence-hit')
    return
  }
  const hb = host.getBoundingClientRect()
  const range = document.createRange()
  for (const r of ranges) {
    const a = Math.max(0, r.start)
    const b = Math.min(tn.length, r.end)
    if (b <= a) continue
    range.setStart(tn, a)
    range.setEnd(tn, b)
    for (const rect of range.getClientRects()) {
      if (rect.width < 0.5 || rect.height < 0.5) continue
      const ov = document.createElement('div')
      ov.className = 'sentence-hit-ov'
      ov.style.left = `${rect.left - hb.left}px`
      ov.style.top = `${rect.top - hb.top}px`
      ov.style.width = `${rect.width}px`
      ov.style.height = `${Math.max(rect.height, 2)}px`
      host.appendChild(ov)
    }
  }
}

function setHoveredSentence(id: string | null) {
  if (hoverClearTimer) {
    clearTimeout(hoverClearTimer)
    hoverClearTimer = null
  }
  if (id) {
    applySentenceHover(id)
    return
  }
  hoverClearTimer = setTimeout(() => {
    applySentenceHover(pinnedSentence.value?.id ?? null)
    hoverClearTimer = null
  }, 40)
}

function nodeContainsSentence(el: HTMLElement, id: string): boolean {
  const ids = `${el.dataset.sentenceIds || ''},${el.dataset.sentenceId || ''}`
  if (ids.split(',').includes(id)) return true
  return decodeSentRanges(el.dataset.sentRanges).some((range) => range.id === id)
}

async function locateSourceSentence(id: string) {
  await nextTick()
  const root = scrollRef.value
  if (!root) return
  const source = [...root.querySelectorAll<HTMLElement>('[data-left-pane] [data-sentence-id]')].find(
    (el) => nodeContainsSentence(el, id),
  )
  if (!source) return
  const rootRect = root.getBoundingClientRect()
  const sourceRect = source.getBoundingClientRect()
  const top = root.scrollTop + sourceRect.top - rootRect.top - root.clientHeight * 0.42
  root.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
}

function clearPinnedSentence() {
  pinnedSentence.value = null
  applySentenceHover(null)
}

function togglePinnedSentence(id: string, page: number, block: ContentBlock) {
  if (window.getSelection()?.toString().trim()) return
  if (pinnedSentence.value?.id === id) {
    clearPinnedSentence()
    return
  }
  pinnedSentence.value = { id, page, blockId: block.id, fallback: blockDisplay(page, block).text }
  applySentenceHover(id)
  void locateSourceSentence(id)
}

const pinnedSentenceText = computed(() => {
  const pinned = pinnedSentence.value
  if (!pinned) return ''
  const page = pages.value.find((item) => item.page === pinned.page)
  const block = page?.blocks.find((item) => item.id === pinned.blockId)
  if (block) return blockDisplay(pinned.page, block).text
  return pinned.fallback
})

type SentencePart = {
  id: string
  gap: string
  chunks: RichChunk[]
  pending: boolean
}

function sentenceRenderParts(pageNo: number, block: ContentBlock): SentencePart[] {
  const sents = pageSentences(pageNo, block)
  if (!sents.length) {
    // 该块只有跨页句子的后续物理片段，右栏应在句子起始页显示完整内容。
    if ((block.sentences || []).length) return []
    const chunks = blockRichChunks(pageNo, block)
    if (!chunks.length) return []
    return [{ id: `block:${block.id}`, gap: '', chunks, pending: false }]
  }
  const parts: SentencePart[] = []
  for (let i = 0; i < sents.length; i++) {
    const sent = sents[i]!
    const view = sentenceView(pageNo, sent)
    const gap = i ? joinGap(sentenceView(pageNo, sents[i - 1]!).text, view.text) : ''
    parts.push({
      id: sent.id,
      gap,
      chunks: splitInlineMath(view.text),
      pending: view.pending,
    })
  }
  return parts
}

function joinGap(prev: string, next: string): string {
  if (!prev) return ''
  if (/[\u4e00-\u9fff。！？；：]$/.test(prev.trim()) && /^[\u4e00-\u9fff「“（]/.test(next.trim())) {
    return ''
  }
  return ' '
}

function blockTypeClass(block: ContentBlock) {
  return {
    'text-lg font-semibold': block.type === 'title',
    'font-semibold': block.type === 'section',
    'text-sm italic text-muted-foreground': block.type === 'caption' || isFigureCaption(block),
  }
}

function pageBlocks(pageNo: number): ContentBlock[] {
  const p = pages.value.find((x) => x.page === pageNo)
  if (!p) return []
  return [...p.blocks]
    .filter((block) => !(block.sentences || []).length || pageSentences(pageNo, block).length > 0)
    .sort((a, b) => a.order - b.order || a.bbox[1] - b.bbox[1])
}

function figureSrc(block: ContentBlock): string | null {
  const path = block.meta?.image_path
  return typeof path === 'string' && path ? paperAssetUrl(props.paperId, path) : null
}

type FigureCell = { figure: ContentBlock; caption?: ContentBlock }
type RightPaneItem =
  | { kind: 'block'; id: string; block: ContentBlock }
  | { kind: 'figure-group'; id: string; cells: FigureCell[] }

function isSubfigureCaption(block: ContentBlock | undefined): boolean {
  return !!block && block.type === 'caption' && /^\s*\([a-z0-9]+\)\s*$/i.test(block.source_text || '')
}

function figuresShareRow(a: ContentBlock, b: ContentBlock): boolean {
  const [, ay0 = 0, , ay1 = 0] = a.bbox ?? []
  const [, by0 = 0, , by1 = 0] = b.bbox ?? []
  const overlap = Math.max(0, Math.min(ay1, by1) - Math.max(ay0, by0))
  return overlap >= Math.min(Math.max(1, ay1 - ay0), Math.max(1, by1 - by0)) * 0.5
}

function rightPaneItems(pageNo: number): RightPaneItem[] {
  const blocks = pageBlocks(pageNo)
  const items: RightPaneItem[] = []
  for (let i = 0; i < blocks.length; ) {
    const block = blocks[i]!
    if (block.type !== 'figure' || !figureSrc(block)) {
      items.push({ kind: 'block', id: block.id, block })
      i += 1
      continue
    }

    const cells: FigureCell[] = []
    const firstFigure = block
    while (i < blocks.length) {
      const figure = blocks[i]
      if (!figure || figure.type !== 'figure' || !figureSrc(figure)) break
      if (cells.length && !figuresShareRow(firstFigure, figure)) break
      const caption = isSubfigureCaption(blocks[i + 1]) ? blocks[i + 1] : undefined
      cells.push({ figure, caption })
      i += caption ? 2 : 1
    }
    items.push({ kind: 'figure-group', id: `figures:${cells.map((cell) => cell.figure.id).join(':')}`, cells })
  }
  return items
}

function figureGroupBounds(cells: FigureCell[]) {
  const blocks = cells.flatMap((cell) => (cell.caption ? [cell.figure, cell.caption] : [cell.figure]))
  const xs0 = blocks.map((block) => block.bbox?.[0] ?? 0)
  const ys0 = blocks.map((block) => block.bbox?.[1] ?? 0)
  const xs1 = blocks.map((block) => block.bbox?.[2] ?? 1)
  const ys1 = blocks.map((block) => block.bbox?.[3] ?? 1)
  const x0 = Math.min(...xs0)
  const y0 = Math.min(...ys0)
  const x1 = Math.max(...xs1)
  const y1 = Math.max(...ys1)
  return { x0, y0, x1, y1, width: Math.max(1, x1 - x0), height: Math.max(1, y1 - y0) }
}

function figureGroupStyle(cells: FigureCell[], pageWidth: number) {
  const bounds = figureGroupBounds(cells)
  const widthPct = pageWidth > 0 ? (bounds.width / pageWidth) * 100 : 100
  return {
    width: `${Math.min(100, Math.max(28, widthPct))}%`,
    maxWidth: '100%',
    aspectRatio: `${bounds.width} / ${bounds.height}`,
  }
}

function figureGroupItemStyle(block: ContentBlock, cells: FigureCell[]) {
  const bounds = figureGroupBounds(cells)
  const [x0 = 0, y0 = 0, x1 = 1, y1 = 1] = block.bbox ?? []
  return {
    left: `${((x0 - bounds.x0) / bounds.width) * 100}%`,
    top: `${((y0 - bounds.y0) / bounds.height) * 100}%`,
    width: `${((x1 - x0) / bounds.width) * 100}%`,
    height: `${((y1 - y0) / bounds.height) * 100}%`,
  }
}

function figureImageStyle(block: ContentBlock, cells: FigureCell[]) {
  return {
    ...figureGroupItemStyle(block, cells),
    objectFit: 'contain' as const,
  }
}

function figureIsCentered(block: ContentBlock, pageWidth: number): boolean {
  const [x0 = 0, , x1 = 0] = block.bbox ?? []
  if (pageWidth <= 0) return true
  const left = x0
  const right = pageWidth - x1
  return Math.abs(left - right) < Math.max(18, pageWidth * 0.06)
}

function isFigureCaption(block: ContentBlock): boolean {
  if (block.type === 'caption') return true
  return /^\s*Figure\s+\d+/i.test(block.source_text || '')
}

function blockTextAlign(block: ContentBlock, pageWidth: number): string {
  if (block.type === 'formula') return 'text-center'
  if (isFigureCaption(block) && figureIsCentered(block, pageWidth)) return 'text-center'
  return 'text-left'
}

watch(
  () => props.fontScale,
  async () => {
    await nextTick()
    const next = { ...rightOffsets.value }
    let changed = false
    for (const pane of scrollRef.value?.querySelectorAll<HTMLElement>('[data-right-pane]') ?? []) {
      const pageNo = rightPanePageNo(pane)
      const max = rightContentMax(pane)
      const cur = next[pageNo] ?? 0
      const clamped = Math.min(cur, max)
      if (clamped !== cur) {
        next[pageNo] = clamped
        changed = true
      }
    }
    if (changed) rightOffsets.value = next
  },
)

watch(
  () => props.paperId,
  () => {
    stopTranslate()
    clearPinnedSentence()
    translationPages.value = {}
    rightOffsets.value = {}
    activeSlide = null
    void bootstrap()
  },
)

watch(
  () => [props.splitPercent, pages.value.length] as const,
  async () => {
    await nextTick()
    updateFitScale()
  },
)

watch(scrollRef, (el, prev) => {
  bindOuterWheel(el, prev)
})

onMounted(async () => {
  await bootstrap()
  await nextTick()
  updateFitScale()
  window.addEventListener('keydown', onWindowKeydown)
  window.addEventListener('keyup', onWindowKeyup)
  if (typeof ResizeObserver !== 'undefined' && scrollRef.value) {
    let roRaf = 0
    resizeObserver = new ResizeObserver(() => {
      if (roRaf) return
      roRaf = requestAnimationFrame(() => {
        roRaf = 0
        updateFitScale()
      })
    })
    resizeObserver.observe(scrollRef.value)
  }
})

onBeforeUnmount(() => {
  stopPolling()
  stopTranslate()
  stopPan()
  bindOuterWheel(null, scrollRef.value)
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  resizeObserver?.disconnect()
  resizeObserver = null
  if (hoverClearTimer) clearTimeout(hoverClearTimer)
  window.removeEventListener('keydown', onWindowKeydown)
  window.removeEventListener('keyup', onWindowKeyup)
})

defineExpose({ scrollToPage })
</script>

<template>
  <div class="relative flex h-full min-h-0 flex-col bg-[#f2ede6]">
    <!-- 解析状态条 -->
    <div
      v-if="paper && paper.status !== 'ready'"
      class="shrink-0 border-b border-border/50 bg-[#f7f3ec] px-3 py-2 text-xs"
    >
      <div class="flex items-center gap-2">
        <Loader2 v-if="isParsing" class="h-3.5 w-3.5 animate-spin text-primary" />
        <AlertCircle v-else-if="paper.status === 'failed'" class="h-3.5 w-3.5 text-destructive" />
        <span class="min-w-0 flex-1 text-muted-foreground">
          {{ STATUS_LABEL[paper.status] }}
          <template v-if="paper.error_message"> · {{ paper.error_message }}</template>
          <template v-else-if="isParsing">
            · {{ parseProgressHint }}
            <span v-if="parseProgressPct > 0" class="tabular-nums">（{{ parseProgressPct }}%）</span>
          </template>
          <template v-else-if="paper.status === 'uploaded'"> · 尚未解析，正在自动开始…</template>
        </span>
        <button
          v-if="needsParse"
          type="button"
          class="ml-auto inline-flex items-center gap-1 rounded-lg border border-border bg-white px-2 py-1 hover:bg-[#f2ede6]"
          :disabled="retrying"
          @click="onRetry"
        >
          <RefreshCw class="h-3.5 w-3.5" :class="retrying && 'animate-spin'" />
          {{ paper.status === 'failed' ? '重试解析' : '开始解析' }}
        </button>
      </div>
      <div v-if="isParsing" class="mt-2 h-1.5 overflow-hidden rounded-full bg-border/60">
        <div
          class="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
          :style="{ width: `${parseProgressPct}%` }"
        />
      </div>
    </div>

    <div
      v-if="loading"
      class="flex flex-1 items-center justify-center text-muted-foreground"
    >
      <Loader2 class="h-6 w-6 animate-spin" />
    </div>

    <div
      v-else-if="error"
      class="m-4 flex items-start gap-2 rounded-xl border border-destructive/30 bg-white px-3 py-2 text-sm text-destructive"
    >
      <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p>{{ error }}</p>
        <button type="button" class="mt-2 text-xs underline" @click="bootstrap">重试加载</button>
      </div>
    </div>

    <div
      v-else-if="!documentModel"
      class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground"
    >
      <Loader2 v-if="isParsing || retrying" class="h-6 w-6 animate-spin text-primary" />
      <p v-if="isParsing || retrying">解析进行中，请稍候…</p>
      <p v-else-if="needsParse">这篇论文还没有结构化结果，请点击开始解析。</p>
      <p v-else>暂无结构化文档。</p>
      <button
        v-if="needsParse && !retrying"
        type="button"
        class="mt-2 inline-flex items-center gap-1 rounded-lg border border-border bg-white px-3 py-1.5 text-xs"
        @click="onRetry"
      >
        <RefreshCw class="h-3.5 w-3.5" />
        开始解析
      </button>
    </div>

    <div
      v-else
      ref="scrollRef"
      class="min-h-0 flex-1 overflow-y-auto overflow-x-hidden"
      @scroll="onScroll"
    >
      <div
        v-if="pinnedSentence"
        class="pointer-events-none sticky top-2 z-40 ml-auto h-0 px-3"
        :style="{ width: `${100 - leftPct}%` }"
      >
        <div
          class="pointer-events-auto ml-1 rounded-lg border border-amber-300/80 bg-amber-50/95 px-3 py-2 shadow-lg backdrop-blur"
        >
          <div class="mb-1 flex items-center gap-2 text-[11px] text-amber-800/80">
            <span>已固定对照 · 原文第 {{ pinnedSentence.page }} 页</span>
            <span class="ml-auto">点击其他句子更新 · Esc 取消</span>
            <button
              type="button"
              class="rounded px-1 text-base leading-none text-amber-900/70 hover:bg-amber-200/70"
              title="取消固定对照"
              @click="clearPinnedSentence"
            >
              ×
            </button>
          </div>
          <p class="m-0 leading-relaxed text-foreground" :style="{ fontSize: `${fontPx}px` }">
            {{ pinnedSentenceText }}
          </p>
        </div>
      </div>
      <div class="w-full py-3">
        <div
          v-for="page in pages"
          :key="`row-${page.page}`"
          class="flex w-full min-w-0"
          :data-page="page.page"
          :style="{
            height: `${page.height * renderScale}px`,
            marginBottom: `${PAGE_GAP}px`,
          }"
        >
          <div
            data-left-pane
            class="h-full min-w-0 overflow-x-auto overflow-y-hidden bg-[#f2ede6] px-1"
            :class="spacePressed ? (panning ? 'cursor-grabbing select-none' : 'cursor-grab') : ''"
            :style="{ width: `${leftPct}%` }"
            @scroll="onLeftPaneScroll"
            @pointerdown.capture="startPan"
            @pointermove="movePan"
            @pointerup="stopPan"
            @pointercancel="stopPan"
          >
            <div
              class="relative mx-auto"
              :style="{
                width: `${page.width * renderScale}px`,
                height: `${page.height * renderScale}px`,
              }"
            >
              <LayoutPage
                :paper-id="paperId"
                :page="page"
                :scale="renderScale"
                @hover-sentence="setHoveredSentence"
              />
              <div
                class="pointer-events-none absolute right-2 top-2 rounded bg-black/40 px-1.5 py-0.5 text-[10px] text-white"
              >
                {{ page.page }} / {{ documentModel.page_count }}
              </div>
            </div>
          </div>

          <div class="w-1.5 shrink-0 self-stretch bg-border/70" />

          <div class="h-full min-w-0 flex-1 overflow-hidden bg-[#f2ede6] px-1">
            <div class="flex h-full w-full flex-col overflow-hidden bg-white shadow-sm ring-1 ring-black/5">
              <div data-right-pane class="relative h-full overflow-clip">
                <div
                  data-right-content
                  class="absolute left-0 right-0 top-0 px-4 py-3"
                  :style="{ transform: `translate3d(0, ${-(rightOffsets[page.page] || 0)}px, 0)` }"
                >
                <template v-if="rightPaneItems(page.page).length">
                  <template v-for="item in rightPaneItems(page.page)" :key="item.id">
                    <div
                      v-if="item.kind === 'figure-group'"
                      class="relative mx-auto mb-5 overflow-hidden rounded-sm bg-[#faf7f2]"
                      :style="figureGroupStyle(item.cells, page.width)"
                    >
                      <template v-for="cell in item.cells" :key="cell.figure.id">
                        <img
                          :src="figureSrc(cell.figure)!"
                          :alt="`figure-${cell.figure.id}`"
                          class="absolute box-border rounded-sm border border-border/40 bg-white"
                          :style="figureImageStyle(cell.figure, item.cells)"
                        />
                        <p
                          v-if="cell.caption"
                          class="absolute m-0 text-center italic leading-none text-muted-foreground"
                          :style="{
                            ...figureGroupItemStyle(cell.caption, item.cells),
                            fontSize: `${Math.min(fontPx, 12)}px`,
                          }"
                        >
                          {{ blockDisplay(page.page, cell.caption).text }}
                          <span
                            v-if="blockDisplay(page.page, cell.caption).pending"
                            class="ml-1 text-[9px] text-muted-foreground/70"
                          >
                            翻译中
                          </span>
                        </p>
                      </template>
                    </div>
                    <template v-else v-for="block in [item.block]" :key="block.id">
                    <p
                      v-if="block.type === 'formula' && block.segments?.length"
                      class="mb-5 leading-[1.8] text-foreground/90"
                      :class="blockTextAlign(block, page.width)"
                      :data-sentence-id="block.sentences?.[0]?.id || `block:${block.id}`"
                      :style="{ fontSize: `${fontPx}px` }"
                      @pointerenter="
                        setHoveredSentence(block.sentences?.[0]?.id || `block:${block.id}`)
                      "
                      @pointerleave="setHoveredSentence(null)"
                    >
                      <template v-for="(seg, si) in block.segments" :key="`${block.id}-seg-${si}`">
                        <KatexView
                          v-if="seg.kind === 'math' && seg.latex"
                          class="mx-0.5"
                          :latex="seg.latex"
                          :display="true"
                          :title="seg.latex"
                        />
                        <span v-else>{{ seg.text }}</span>
                      </template>
                    </p>
                    <ul
                      v-else-if="block.type === 'list_item'"
                      class="mb-5 list-disc pl-5 leading-[1.8] text-foreground/90"
                      :style="{ fontSize: `${fontPx}px` }"
                    >
                      <li :class="blockTextAlign(block, page.width)">
                        <template
                          v-for="part in sentenceRenderParts(page.page, block)"
                          :key="part.id"
                        >
                          <span v-if="part.gap">{{ part.gap }}</span>
                          <span
                            class="sentence-chip cursor-pointer rounded-sm"
                            :data-sentence-id="part.id"
                            title="点击定位原文并固定翻译"
                            @pointerenter="setHoveredSentence(part.id)"
                            @pointerleave="setHoveredSentence(null)"
                            @click="togglePinnedSentence(part.id, page.page, block)"
                          >
                            <template v-for="(chunk, ci) in part.chunks" :key="`${part.id}-c-${ci}`">
                              <KatexView
                                v-if="chunk.kind === 'math'"
                                class="mx-0.5"
                                :latex="chunk.text"
                                :display="!!chunk.display"
                                :title="chunk.text"
                              />
                              <span v-else>{{ chunk.text }}</span>
                            </template>
                          </span>
                        </template>
                      </li>
                    </ul>
                    <p
                      v-else-if="sentenceRenderParts(page.page, block).length"
                      class="mb-5 leading-[1.8] text-foreground/90"
                      :class="[blockTextAlign(block, page.width), blockTypeClass(block)]"
                      :style="{ fontSize: block.type === 'title' ? undefined : `${fontPx}px` }"
                    >
                      <template
                        v-for="part in sentenceRenderParts(page.page, block)"
                        :key="part.id"
                      >
                        <span v-if="part.gap">{{ part.gap }}</span>
                        <span
                          class="sentence-chip cursor-pointer rounded-sm"
                          :data-sentence-id="part.id"
                          title="点击定位原文并固定翻译"
                          @pointerenter="setHoveredSentence(part.id)"
                          @pointerleave="setHoveredSentence(null)"
                          @click="togglePinnedSentence(part.id, page.page, block)"
                        >
                          <template v-for="(chunk, ci) in part.chunks" :key="`${part.id}-c-${ci}`">
                            <KatexView
                              v-if="chunk.kind === 'math'"
                              class="mx-0.5"
                              :latex="chunk.text"
                              :display="!!chunk.display"
                              :title="chunk.text"
                            />
                            <span v-else>{{ chunk.text }}</span>
                          </template>
                        </span>
                      </template>
                      <span
                        v-if="blockDisplay(page.page, block).pending"
                        class="ml-1 text-[10px] text-muted-foreground/70"
                      >
                        翻译中
                      </span>
                    </p>
                    </template>
                  </template>
                </template>
                <p v-else class="text-sm text-muted-foreground">本页无内容</p>
                </div>
                <div
                  class="pointer-events-none absolute right-0.5 top-1 bottom-1 w-1 overflow-hidden rounded-full"
                >
                  <div
                    class="w-full rounded-full bg-black/20"
                    :style="rightThumbStyle(page.page, page.height * renderScale)"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sentence-hit,
.sentence-chip.sentence-hit,
:deep(.sentence-hit) {
  background-color: rgb(253 224 71 / 0.42);
  box-shadow: 0 0 0 2px rgb(245 158 11 / 0.28);
  border-radius: 2px;
}
:deep(.sentence-hit-ov) {
  position: absolute;
  z-index: 0;
  pointer-events: none;
  border-radius: 2px;
  background-color: rgb(253 224 71 / 0.42);
  box-shadow: 0 0 0 1px rgb(245 158 11 / 0.2);
}
</style>
