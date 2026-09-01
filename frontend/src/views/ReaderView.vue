<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { AlertCircle, ArrowLeft, Languages, Loader2, Minus, Plus, RotateCcw } from 'lucide-vue-next'
import SplitDocumentView from '@/components/reader/SplitDocumentView.vue'
import ReaderRightRail from '@/components/reader/ReaderRightRail.vue'
import { usePapersStore } from '@/stores/papers'
import { useUiStore } from '@/stores/ui'
import type { Paper } from '@/types'
import { STATUS_LABEL } from '@/types'

const props = defineProps<{
  id: string
}>()

const store = usePapersStore()
const uiStore = useUiStore()
const router = useRouter()
const {
  readerPdfScale: pdfScale,
  readerTextScale: textScale,
  readerSplitPercent: splitPercent,
} = storeToRefs(uiStore)

const loadingMeta = ref(true)
const error = ref('')

const page = ref(1)
const pageCount = ref(0)
const pageInput = ref('1')
const paperStatus = ref<Paper['status'] | null>(null)

const docRef = ref<InstanceType<typeof SplitDocumentView> | null>(null)
const splitRowRef = ref<HTMLElement | null>(null)
const dragging = ref(false)
const translateBusy = ref(false)
const translateProgress = ref('')
const toast = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null

const paper = computed(() => store.items.find((p) => p.id === props.id) ?? null)
const title = computed(() => paper.value?.title || paper.value?.filename || '论文')

function showToast(msg: string) {
  toast.value = msg
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value = ''
    toastTimer = null
  }, 3200)
}

function unwrapMaybeRef<T>(v: T | { value: T } | undefined | null): T | undefined {
  if (v == null) return undefined
  if (typeof v === 'object' && v !== null && 'value' in v) return (v as { value: T }).value
  return v as T
}

async function onTranslateAll() {
  const doc = docRef.value
  if (!doc || translateBusy.value) return
  translateBusy.value = true
  translateProgress.value = '排队中…'
  const tick = window.setInterval(() => {
    const running = unwrapMaybeRef(doc.translateAllRunning)
    const done = unwrapMaybeRef(doc.translateAllDone) ?? 0
    const total = unwrapMaybeRef(doc.translateAllTotal) ?? 0
    if (running && total > 0) translateProgress.value = `${done}/${total}`
  }, 200)
  try {
    const result = await doc.translateAllPages()
    if (result === 'unconfigured') {
      showToast('尚未配置翻译模型，请先到设置页填写 Base URL 与 Model')
    } else if (result === 'done') {
      showToast('全部页面已有译文')
    } else {
      showToast('全文翻译完成')
    }
  } catch (e) {
    showToast(e instanceof Error ? e.message : String(e))
  } finally {
    clearInterval(tick)
    translateBusy.value = false
    translateProgress.value = ''
  }
}

onMounted(async () => {
  loadingMeta.value = true
  error.value = ''
  try {
    const p = await store.getOne(props.id)
    paperStatus.value = p.status
    if (p.page_count) pageCount.value = p.page_count
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loadingMeta.value = false
  }
})

function onPageChange(p: number) {
  page.value = p
  pageInput.value = String(p)
}

function onPaperUpdate(p: Paper) {
  paperStatus.value = p.status
  const idx = store.items.findIndex((x) => x.id === p.id)
  if (idx >= 0) store.items[idx] = p
  else store.items.unshift(p)
}

function jumpToPage() {
  const n = Number.parseInt(pageInput.value, 10)
  if (!Number.isFinite(n) || !pageCount.value) {
    pageInput.value = String(page.value)
    return
  }
  const clamped = Math.min(Math.max(1, n), pageCount.value)
  page.value = clamped
  pageInput.value = String(clamped)
  docRef.value?.scrollToPage(clamped)
}

function pdfZoomBy(delta: number) {
  pdfScale.value = Math.min(2.4, Math.max(0.55, Number((pdfScale.value + delta).toFixed(2))))
}

function textZoomBy(delta: number) {
  textScale.value = Math.min(2, Math.max(0.75, Number((textScale.value + delta).toFixed(2))))
}

function onSplitPointerDown(e: PointerEvent) {
  e.preventDefault()
  dragging.value = true
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  window.addEventListener('pointermove', onSplitPointerMove)
  window.addEventListener('pointerup', onSplitPointerUp)
}

function onSplitPointerMove(e: PointerEvent) {
  if (!dragging.value || !splitRowRef.value) return
  const rect = splitRowRef.value.getBoundingClientRect()
  const ratio = ((e.clientX - rect.left) / rect.width) * 100
  splitPercent.value = Math.min(80, Math.max(20, ratio))
}

function onSplitPointerUp() {
  dragging.value = false
  window.removeEventListener('pointermove', onSplitPointerMove)
  window.removeEventListener('pointerup', onSplitPointerUp)
}

function onKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  if (e.key === '+' || e.key === '=') pdfZoomBy(0.1)
  else if (e.key === '-') pdfZoomBy(-0.1)
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('pointermove', onSplitPointerMove)
  window.removeEventListener('pointerup', onSplitPointerUp)
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <div class="relative flex h-full min-h-0 flex-col bg-[#f2ede6]">
    <p
      v-if="toast"
      class="absolute left-1/2 top-14 z-50 -translate-x-1/2 rounded-lg border border-border/70 bg-white px-3 py-1.5 text-xs shadow-md"
    >
      {{ toast }}
    </p>
    <header
      class="grid h-11 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-border/60 bg-[#f7f3ec]/95 px-2 md:px-3"
    >
      <div class="flex min-w-0 items-center gap-2">
        <button
          type="button"
          class="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg px-2 text-xs text-muted-foreground hover:bg-white/70 hover:text-foreground"
          @click="router.push({ name: 'library' })"
        >
          <ArrowLeft class="h-4 w-4" />
          <span class="hidden sm:inline">论文库</span>
        </button>
        <p class="min-w-0 truncate text-xs font-medium md:text-sm">{{ title }}</p>
        <span
          v-if="paperStatus"
          class="hidden shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] text-muted-foreground ring-1 ring-border/60 sm:inline"
        >
          {{ STATUS_LABEL[paperStatus] }}
        </span>
      </div>

      <div class="flex items-center justify-center gap-2">
        <div
          class="flex items-center gap-1 rounded-lg border border-border/70 bg-white px-2 py-1 text-xs tabular-nums"
        >
          <input
            v-model="pageInput"
            class="w-8 bg-transparent text-center outline-none focus:text-primary"
            @keydown.enter="jumpToPage"
            @blur="jumpToPage"
          />
          <span class="text-muted-foreground">/ {{ pageCount || '—' }}</span>
        </div>

        <div class="flex items-center gap-0.5 rounded-lg border border-border/70 bg-white p-0.5">
          <span class="hidden px-1.5 text-[10px] text-muted-foreground sm:inline">版式</span>
          <button
            type="button"
            class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2ede6]"
            @click="pdfZoomBy(-0.1)"
          >
            <Minus class="h-3.5 w-3.5" />
          </button>
          <span class="min-w-9 text-center text-[11px] tabular-nums text-muted-foreground">
            {{ Math.round(pdfScale * 100) }}%
          </span>
          <button
            type="button"
            class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2ede6]"
            @click="pdfZoomBy(0.1)"
          >
            <Plus class="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2ede6]"
            @click="pdfScale = 1"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
        </div>

        <div class="flex items-center gap-0.5 rounded-lg border border-border/70 bg-white p-0.5">
          <span class="hidden px-1.5 text-[10px] text-muted-foreground sm:inline">文本</span>
          <button
            type="button"
            class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2ede6]"
            @click="textZoomBy(-0.1)"
          >
            <Minus class="h-3.5 w-3.5" />
          </button>
          <span class="min-w-9 text-center text-[11px] tabular-nums text-muted-foreground">
            {{ Math.round(textScale * 100) }}%
          </span>
          <button
            type="button"
            class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2ede6]"
            @click="textZoomBy(0.1)"
          >
            <Plus class="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[#f2ede6]"
            @click="textScale = 1"
          >
            <RotateCcw class="h-3.5 w-3.5" />
          </button>
        </div>

        <button
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border/70 bg-white px-2.5 text-xs text-foreground hover:bg-[#f2ede6] disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="translateBusy || !pageCount"
          :title="translateBusy ? '正在逐页翻译…' : '不等待滑动，排队翻译全部页面'"
          @click="onTranslateAll"
        >
          <Loader2 v-if="translateBusy" class="h-3.5 w-3.5 animate-spin" />
          <Languages v-else class="h-3.5 w-3.5" />
          <span>{{ translateBusy ? `翻译中 ${translateProgress}` : '全文翻译' }}</span>
        </button>
      </div>

      <div class="justify-self-end" />
    </header>

    <div v-if="loadingMeta" class="flex flex-1 items-center justify-center text-muted-foreground">
      <Loader2 class="h-7 w-7 animate-spin" />
    </div>

    <div
      v-else-if="error"
      class="m-4 flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive"
    >
      <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p class="font-medium">无法打开论文</p>
        <p class="mt-1">{{ error }}</p>
      </div>
    </div>

    <div v-else class="relative flex min-h-0 flex-1">
      <div ref="splitRowRef" class="relative min-w-0 flex-1" :class="dragging && 'select-none'">
        <SplitDocumentView
          ref="docRef"
          :paper-id="id"
          :pdf-scale="pdfScale"
          :font-scale="textScale"
          :split-percent="splitPercent"
          @update:page="onPageChange"
          @page-count="pageCount = $event"
          @paper-update="onPaperUpdate"
        />

        <div
          class="absolute inset-y-0 z-20 w-3 -translate-x-1/2 cursor-col-resize"
          :style="{ left: `${splitPercent}%` }"
          title="拖动调整左右宽度"
          @pointerdown="onSplitPointerDown"
        >
          <div
            class="absolute inset-y-0 left-1/2 w-1.5 -translate-x-1/2 transition-colors"
            :class="dragging ? 'bg-primary/50' : 'bg-transparent hover:bg-primary/30'"
          />
        </div>
      </div>

      <ReaderRightRail />
    </div>
  </div>
</template>
