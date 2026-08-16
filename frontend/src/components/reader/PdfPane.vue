<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as pdfjs from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { Loader2 } from 'lucide-vue-next'
import type { PageTextBlock, PageTextLine } from '@/types/reader'

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker

const props = withDefaults(
  defineProps<{
    src: string
    scale?: number
  }>(),
  { scale: 1.1 },
)

const emit = defineEmits<{
  'update:page': [page: number]
  'page-count': [count: number]
  'page-heights': [heights: number[]]
  'pages-text': [blocks: PageTextBlock[]]
  error: [message: string]
  'loading-change': [loading: boolean]
  scroll: [scrollTop: number]
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const loading = ref(true)
const pageCount = ref(0)
const currentPage = ref(1)
const pageHeights = ref<number[]>([])
const pageGaps = 12

let pdfDoc: pdfjs.PDFDocumentProxy | null = null
let loadToken = 0
const renderTasks = new Map<number, pdfjs.RenderTask>()
const renderTokens = new Map<number, number>()
let observer: IntersectionObserver | null = null
let scrollRaf = 0
let suppressScrollEmit = false

interface PdfTextItem {
  str: string
  transform: number[]
}

interface LineDraft {
  text: string
  x: number
  y: number
  xEnd: number
  topRatio: number
}

function isTextItem(item: unknown): item is PdfTextItem {
  return !!item && typeof item === 'object' && 'str' in item && 'transform' in item
}

function buildLines(items: PdfTextItem[], viewport: pdfjs.PageViewport): PageTextLine[] {
  type Raw = { text: string; x: number; y: number; h: number }
  const raw: Raw[] = []

  for (const item of items) {
    const str = item.str?.trim()
    if (!str) continue
    const tx = pdfjs.Util.transform(viewport.transform, item.transform)
    const x = tx[4] ?? 0
    const y = tx[5] ?? 0
    const h = Math.hypot(tx[2] ?? 0, tx[3] ?? 0) || 12
    raw.push({ text: str, x, y, h })
  }

  raw.sort((a, b) => b.y - a.y || a.x - b.x)
  const lines: LineDraft[] = []
  const threshold = 6

  for (const item of raw) {
    const last = lines[lines.length - 1]
    if (last && Math.abs(last.y - item.y) <= Math.max(threshold, item.h * 0.35)) {
      const gap = item.x - last.xEnd
      last.text += gap > item.h * 0.25 ? ` ${item.text}` : item.text
      last.xEnd = item.x + item.text.length * (item.h * 0.45)
    } else {
      lines.push({
        text: item.text,
        x: item.x,
        y: item.y,
        xEnd: item.x + item.text.length * (item.h * 0.45),
        topRatio: 1 - item.y / viewport.height,
      })
    }
  }

  return lines.map(({ text, x, y, topRatio }) => ({ text, x, y, topRatio }))
}

async function measurePages() {
  if (!pdfDoc) return
  const heights: number[] = []
  for (let i = 1; i <= pdfDoc.numPages; i++) {
    const page = await pdfDoc.getPage(i)
    const viewport = page.getViewport({ scale: props.scale, rotation: page.rotate })
    heights.push(Math.ceil(viewport.height))
  }
  pageHeights.value = heights
  emit('page-heights', [...heights])
}

async function extractAllText() {
  if (!pdfDoc) return
  const blocks: PageTextBlock[] = []
  for (let i = 1; i <= pdfDoc.numPages; i++) {
    const page = await pdfDoc.getPage(i)
    const viewport = page.getViewport({ scale: 1, rotation: page.rotate })
    const content = await page.getTextContent()
    const textItems: PdfTextItem[] = []
    for (const item of content.items) {
      if (isTextItem(item)) textItems.push(item)
    }
    blocks.push({ page: i, lines: buildLines(textItems, viewport) })
  }
  emit('pages-text', blocks)
}

async function renderIntoCanvas(pageNumber: number, canvas: HTMLCanvasElement) {
  if (!pdfDoc) return

  const prev = renderTasks.get(pageNumber)
  if (prev) {
    try {
      prev.cancel()
    } catch {
      /* ignore */
    }
    renderTasks.delete(pageNumber)
  }

  const token = (renderTokens.get(pageNumber) ?? 0) + 1
  renderTokens.set(pageNumber, token)

  const page = await pdfDoc.getPage(pageNumber)
  if (renderTokens.get(pageNumber) !== token) return

  const viewport = page.getViewport({ scale: props.scale, rotation: page.rotate })
  const context = canvas.getContext('2d')
  if (!context) return

  const outputScale = window.devicePixelRatio || 1
  const cssWidth = Math.floor(viewport.width)
  const cssHeight = Math.floor(viewport.height)
  canvas.width = Math.floor(cssWidth * outputScale)
  canvas.height = Math.floor(cssHeight * outputScale)
  canvas.style.width = `${cssWidth}px`
  canvas.style.height = `${cssHeight}px`

  // 重置 2D 状态，避免残留 transform 导致倒置/错位
  context.setTransform(1, 0, 0, 1, 0, 0)
  context.clearRect(0, 0, canvas.width, canvas.height)
  context.setTransform(outputScale, 0, 0, outputScale, 0, 0)

  const task = page.render({
    canvasContext: context,
    viewport,
  })
  renderTasks.set(pageNumber, task)
  try {
    await task.promise
  } catch (e) {
    if ((e as { name?: string })?.name !== 'RenderingCancelledException') throw e
  } finally {
    if (renderTasks.get(pageNumber) === task) renderTasks.delete(pageNumber)
  }
}

function setupObserver() {
  observer?.disconnect()
  const root = containerRef.value
  if (!root) return

  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const pageNum = Number((entry.target as HTMLElement).dataset.page)
        if (!Number.isFinite(pageNum)) continue
        const canvas = entry.target.querySelector('canvas')
        if (canvas) void renderIntoCanvas(pageNum, canvas as HTMLCanvasElement)
      }
    },
    { root, rootMargin: '120% 0px', threshold: 0.01 },
  )

  root.querySelectorAll('[data-page]').forEach((el) => observer?.observe(el))
}

function updateCurrentPageFromScroll() {
  const el = containerRef.value
  if (!el || !pageHeights.value.length) return

  const mid = el.scrollTop + el.clientHeight * 0.3
  let acc = 0
  let page = 1
  for (let i = 0; i < pageHeights.value.length; i++) {
    const h = (pageHeights.value[i] ?? 0) + pageGaps
    if (mid < acc + h) {
      page = i + 1
      break
    }
    acc += h
    page = i + 1
  }
  if (page !== currentPage.value) {
    currentPage.value = page
    emit('update:page', page)
  }
}

function onScroll() {
  const el = containerRef.value
  if (!el) return
  if (!suppressScrollEmit) emit('scroll', el.scrollTop)
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  scrollRaf = requestAnimationFrame(updateCurrentPageFromScroll)
}

async function loadDocument() {
  const token = ++loadToken
  loading.value = true
  emit('loading-change', true)
  try {
    for (const task of renderTasks.values()) {
      try {
        task.cancel()
      } catch {
        /* ignore */
      }
    }
    renderTasks.clear()
    pdfDoc?.destroy()
    pdfDoc = null
    observer?.disconnect()
    pageHeights.value = []

    const doc = await pdfjs.getDocument({ url: props.src }).promise
    if (token !== loadToken) {
      doc.destroy()
      return
    }
    pdfDoc = doc
    pageCount.value = doc.numPages
    emit('page-count', doc.numPages)
    currentPage.value = 1
    emit('update:page', 1)

    await measurePages()
    await nextTick()
    setupObserver()
    await nextTick()

    const canvases = containerRef.value?.querySelectorAll('[data-page] canvas')
    if (canvases?.[0]) await renderIntoCanvas(1, canvases[0] as HTMLCanvasElement)
    if (canvases?.[1]) void renderIntoCanvas(2, canvases[1] as HTMLCanvasElement)
    void extractAllText()
  } catch (e) {
    emit('error', e instanceof Error ? e.message : String(e))
  } finally {
    if (token === loadToken) {
      loading.value = false
      emit('loading-change', false)
    }
  }
}

async function reloadScale() {
  if (!pdfDoc) return
  loading.value = true
  emit('loading-change', true)
  try {
    const el = containerRef.value
    const prevTop = el?.scrollTop ?? 0
    const prevHeight = Math.max(1, el?.scrollHeight ?? 1)
    const ratio = prevTop / prevHeight
    await measurePages()
    await nextTick()
    setupObserver()
    await nextTick()
    el?.querySelectorAll('[data-page]').forEach((wrap) => {
      const pageNum = Number((wrap as HTMLElement).dataset.page)
      const canvas = wrap.querySelector('canvas')
      if (canvas && Number.isFinite(pageNum)) void renderIntoCanvas(pageNum, canvas)
    })
    await nextTick()
    if (el) {
      suppressScrollEmit = true
      el.scrollTop = ratio * el.scrollHeight
      requestAnimationFrame(() => {
        suppressScrollEmit = false
      })
    }
  } finally {
    loading.value = false
    emit('loading-change', false)
  }
}

async function scrollToPage(page: number) {
  const el = containerRef.value
  if (!el || !pageHeights.value.length) return
  const target = Math.min(Math.max(1, page), pageHeights.value.length)
  let top = 0
  for (let i = 0; i < target - 1; i++) top += (pageHeights.value[i] ?? 0) + pageGaps
  suppressScrollEmit = true
  el.scrollTo({ top, behavior: 'smooth' })
  currentPage.value = target
  emit('update:page', target)
  window.setTimeout(() => {
    suppressScrollEmit = false
  }, 320)
}

function setScrollTop(top: number) {
  const el = containerRef.value
  if (!el) return
  suppressScrollEmit = true
  el.scrollTop = top
  requestAnimationFrame(() => {
    suppressScrollEmit = false
  })
}

watch(
  () => props.src,
  () => {
    void loadDocument()
  },
)

watch(
  () => props.scale,
  () => {
    if (pdfDoc) void reloadScale()
  },
)

onMounted(() => {
  void loadDocument()
})

onBeforeUnmount(() => {
  loadToken += 1
  observer?.disconnect()
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  for (const task of renderTasks.values()) {
    try {
      task.cancel()
    } catch {
      /* ignore */
    }
  }
  pdfDoc?.destroy()
  pdfDoc = null
})

defineExpose({ scrollToPage, setScrollTop, pageGaps })
</script>

<template>
  <div
    ref="containerRef"
    class="relative h-full min-h-0 overflow-auto bg-[#f2ede6]"
    @scroll="onScroll"
  >
    <div
      v-if="loading && !pageCount"
      class="absolute inset-0 z-10 flex items-center justify-center bg-[#f2ede6]/80"
    >
      <Loader2 class="h-6 w-6 animate-spin text-primary" />
    </div>

    <div class="flex w-full flex-col items-center px-3 py-3">
      <div
        v-for="(h, idx) in pageHeights"
        :key="`pdf-${idx + 1}-s${scale}`"
        class="relative overflow-hidden bg-white shadow-sm ring-1 ring-black/5"
        :data-page="idx + 1"
        :style="{ height: `${h}px`, marginBottom: `${pageGaps}px` }"
      >
        <canvas class="block" />
        <div
          class="pointer-events-none absolute right-2 top-2 rounded bg-black/45 px-1.5 py-0.5 text-[10px] text-white"
        >
          {{ idx + 1 }} / {{ pageCount }}
        </div>
      </div>
    </div>
  </div>
</template>
