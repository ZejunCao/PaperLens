<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-vue-next'
import LayoutPage from '@/components/reader/LayoutPage.vue'
import KatexView from '@/components/reader/KatexView.vue'
import { fetchDocument, fetchPaper, paperAssetUrl, retryParse } from '@/api/papers'
import type { ContentBlock, DocumentModel } from '@/types/document'
import type { Paper } from '@/types'
import { STATUS_LABEL } from '@/types'

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

let pollTimer: ReturnType<typeof setInterval> | null = null
let scrollRaf = 0
let resizeObserver: ResizeObserver | null = null

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
}

function onScroll() {
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  scrollRaf = requestAnimationFrame(updateCurrentPageFromScroll)
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
}

function pageBlocks(pageNo: number): ContentBlock[] {
  const p = pages.value.find((x) => x.page === pageNo)
  if (!p) return []
  return [...p.blocks].sort((a, b) => a.order - b.order || a.bbox[1] - b.bbox[1])
}

function figureSrc(block: ContentBlock): string | null {
  const path = block.meta?.image_path
  return typeof path === 'string' && path ? paperAssetUrl(props.paperId, path) : null
}

watch(
  () => props.paperId,
  () => {
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
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  resizeObserver?.disconnect()
  resizeObserver = null
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
      class="min-h-0 flex-1 overflow-auto"
      @scroll="onScroll"
    >
      <div class="w-full py-3">
        <div
          v-for="page in pages"
          :key="`row-${page.page}`"
          class="flex w-full"
          :data-page="page.page"
          :style="{
            height: `${page.height * renderScale}px`,
            marginBottom: `${PAGE_GAP}px`,
          }"
        >
          <div
            class="flex h-full items-start justify-center overflow-hidden bg-[#f2ede6] px-1"
            :style="{ width: `${leftPct}%` }"
          >
            <div class="relative w-full">
              <LayoutPage :paper-id="paperId" :page="page" :scale="renderScale" />
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
              <div class="h-full overflow-y-auto overscroll-contain px-4 py-3">
                <template v-if="pageBlocks(page.page).length">
                  <template v-for="block in pageBlocks(page.page)" :key="block.id">
                    <img
                      v-if="block.type === 'figure' && figureSrc(block)"
                      :src="figureSrc(block)!"
                      :alt="`${block.type}-${block.id}`"
                      class="mb-3 max-w-full rounded-sm border border-border/40 bg-[#faf7f2]"
                    />
                    <p
                      v-else-if="block.segments?.length"
                      class="mb-2 text-left leading-relaxed text-foreground/90"
                      :class="{
                        'text-lg font-semibold': block.type === 'title',
                        'font-semibold': block.type === 'section',
                        'text-sm italic text-muted-foreground': block.type === 'caption',
                        'text-center': block.type === 'formula',
                      }"
                      :style="{ fontSize: block.type === 'title' ? undefined : `${fontPx}px` }"
                    >
                      <template v-for="(seg, si) in block.segments" :key="`${block.id}-seg-${si}`">
                        <KatexView
                          v-if="seg.kind === 'math' && seg.latex"
                          class="mx-0.5"
                          :latex="seg.latex"
                          :display="block.type === 'formula' || !!seg.display"
                          :title="seg.latex"
                        />
                        <span v-else>{{ seg.text }}</span>
                      </template>
                    </p>
                    <p
                      v-else-if="block.source_text"
                      class="mb-2 text-left leading-relaxed text-foreground/90"
                      :class="{
                        'text-lg font-semibold': block.type === 'title',
                        'font-semibold': block.type === 'section',
                        'text-sm italic text-muted-foreground': block.type === 'caption',
                      }"
                      :style="{ fontSize: block.type === 'title' ? undefined : `${fontPx}px` }"
                    >
                      {{ block.source_text }}
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
