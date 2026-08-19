<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-vue-next'
import LayoutPage from '@/components/reader/LayoutPage.vue'
import KatexView from '@/components/reader/KatexView.vue'
import { fetchDocument, fetchPaper, paperAssetUrl, retryParse } from '@/api/papers'
import { fetchTranslations, translatePaperPage } from '@/api/settings'
import type { ContentBlock, DocumentModel, Sentence } from '@/types/document'
import type { PageTranslation } from '@/types/translation'
import type { Paper } from '@/types'
import { STATUS_LABEL } from '@/types'
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

function wheelDeltaY(e: WheelEvent): number {
  if (e.deltaMode === WheelEvent.DOM_DELTA_LINE) return e.deltaY * 16
  if (e.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    return e.deltaY * (scrollRef.value?.clientHeight ?? 400)
  }
  return e.deltaY
}

/** 右栏滚到当页顶/底后，继续滚轮则带动整页（左右一起）翻页 */
function onRightPaneWheel(e: WheelEvent) {
  const pane = e.currentTarget as HTMLElement | null
  const outer = scrollRef.value
  if (!pane || !outer || e.deltaY === 0) return
  const dy = wheelDeltaY(e)
  const overflowing = pane.scrollHeight > pane.clientHeight + 1
  if (overflowing) {
    const atBottom = pane.scrollTop + pane.clientHeight >= pane.scrollHeight - 1
    const atTop = pane.scrollTop <= 1
    if (dy > 0 && !atBottom) return
    if (dy < 0 && !atTop) return
  }
  e.preventDefault()
  outer.scrollTop += dy
}

function scrollToPage(page: number) {
  const el = scrollRef.value
  if (!el || !pages.value.length) return
  const target = Math.min(Math.max(1, page), pages.value.length)
  let top = 0
  for (let i = 0; i < target - 1; i++) {
    top += (pages.value[i]?.height ?? 0) * renderScale.value + PAGE_GAP
  }
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
  if (cached?.status === 'ready') return
  if (!llmConfigured.value) return
  dwellTimer = setTimeout(() => {
    void runTranslate(page)
  }, 1000)
}

async function runTranslate(page: number) {
  const key = String(page)
  if (translationPages.value[key]?.status === 'ready') return
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
    applySentenceHover(null)
    hoverClearTimer = null
  }, 40)
}

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

function figureStyle(block: ContentBlock) {
  const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = block.bbox ?? []
  const w = Math.max(1, (x1 - x0) * renderScale.value)
  const h = Math.max(1, (y1 - y0) * renderScale.value)
  return {
    width: `${w}px`,
    maxWidth: '100%',
    aspectRatio: `${w} / ${h}`,
    height: 'auto',
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
  () => props.paperId,
  () => {
    stopTranslate()
    translationPages.value = {}
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
      class="flex shrink-0 items-center gap-2 border-b border-border/50 bg-[#f7f3ec] px-3 py-2 text-xs"
    >
      <Loader2 v-if="isParsing" class="h-3.5 w-3.5 animate-spin text-primary" />
      <AlertCircle v-else-if="paper.status === 'failed'" class="h-3.5 w-3.5 text-destructive" />
      <span class="text-muted-foreground">
        {{ STATUS_LABEL[paper.status] }}
        <template v-if="paper.error_message"> · {{ paper.error_message }}</template>
        <template v-else-if="isParsing"> · 正在结构化解析，完成后左侧将按原版式复现</template>
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
              <div
                class="h-full overflow-y-auto overscroll-contain px-4 py-3"
                @wheel="onRightPaneWheel"
              >
                <template v-if="pageBlocks(page.page).length">
                  <template v-for="block in pageBlocks(page.page)" :key="block.id">
                    <img
                      v-if="block.type === 'figure' && figureSrc(block)"
                      :src="figureSrc(block)!"
                      :alt="`${block.type}-${block.id}`"
                      class="mb-3 rounded-sm border border-border/40 bg-[#faf7f2]"
                      :class="figureIsCentered(block, page.width) ? 'mx-auto block' : ''"
                      :style="figureStyle(block)"
                    />
                    <p
                      v-else-if="block.type === 'formula' && block.segments?.length"
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
                            class="sentence-chip rounded-sm"
                            :data-sentence-id="part.id"
                            @pointerenter="setHoveredSentence(part.id)"
                            @pointerleave="setHoveredSentence(null)"
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
                          class="sentence-chip rounded-sm"
                          :data-sentence-id="part.id"
                          @pointerenter="setHoveredSentence(part.id)"
                          @pointerleave="setHoveredSentence(null)"
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
                <p v-else class="text-sm text-muted-foreground">本页无内容</p>
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
