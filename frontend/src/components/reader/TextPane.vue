<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PageTextBlock } from '@/types/reader'

const props = withDefaults(
  defineProps<{
    page: number
    pageCount: number
    blocks: PageTextBlock[]
    pageHeights: number[]
    pageGaps?: number
    fontScale?: number
    loading?: boolean
  }>(),
  {
    pageGaps: 12,
    fontScale: 1,
  },
)

const emit = defineEmits<{
  scroll: [scrollTop: number]
}>()

const scrollRef = ref<HTMLDivElement | null>(null)
let suppressScrollEmit = false

const fontPx = computed(() => Math.round(14 * (props.fontScale ?? 1)))

const blockMap = computed(() => {
  const map = new Map<number, PageTextBlock>()
  for (const b of props.blocks) map.set(b.page, b)
  return map
})

function onScroll() {
  const el = scrollRef.value
  if (!el || suppressScrollEmit) return
  emit('scroll', el.scrollTop)
}

function setScrollTop(top: number) {
  const el = scrollRef.value
  if (!el) return
  suppressScrollEmit = true
  el.scrollTop = top
  requestAnimationFrame(() => {
    suppressScrollEmit = false
  })
}

function scrollToPage(page: number) {
  const el = scrollRef.value
  if (!el || !props.pageHeights.length) return
  const target = Math.min(Math.max(1, page), props.pageHeights.length)
  let top = 0
  for (let i = 0; i < target - 1; i++) {
    top += (props.pageHeights[i] ?? 0) + props.pageGaps
  }
  suppressScrollEmit = true
  el.scrollTo({ top, behavior: 'smooth' })
  window.setTimeout(() => {
    suppressScrollEmit = false
  }, 320)
}

defineExpose({ setScrollTop, scrollToPage })
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-[#f7f3ec]">
    <div
      class="flex h-9 shrink-0 items-center justify-between border-b border-border/50 bg-[#f2ede6] px-3 text-[11px] text-muted-foreground"
    >
      <span>对照文本 · 第 {{ page }} / {{ pageCount || '—' }} 页</span>
      <span class="rounded-full bg-white/80 px-2 py-0.5 text-[10px] ring-1 ring-border/60">
        暂无译文 · 显示原文
      </span>
    </div>

    <div ref="scrollRef" class="min-h-0 flex-1 overflow-auto px-3 py-3" @scroll="onScroll">
      <div v-if="loading && !pageHeights.length" class="py-10 text-center text-sm text-muted-foreground">
        提取文本中…
      </div>

      <div v-else class="mx-auto flex w-full max-w-3xl flex-col">
        <div
          v-for="(h, idx) in pageHeights"
          :key="`text-page-${idx + 1}`"
          class="overflow-hidden rounded-sm bg-white shadow-sm ring-1 ring-black/5"
          :style="{ height: `${h}px`, marginBottom: `${pageGaps}px` }"
        >
          <div class="flex h-7 items-center justify-between border-b border-border/40 bg-[#faf7f2] px-3">
            <span class="text-[11px] font-medium text-muted-foreground">第 {{ idx + 1 }} 页</span>
            <span class="text-[10px] text-muted-foreground/80">页内可滚动</span>
          </div>
          <div class="h-[calc(100%-1.75rem)] overflow-y-auto px-4 py-3">
            <template v-if="blockMap.get(idx + 1)?.lines?.length">
              <p
                v-for="(line, lineIdx) in blockMap.get(idx + 1)!.lines"
                :key="`${idx + 1}-${lineIdx}`"
                class="mb-1.5 leading-relaxed text-foreground/90"
                :style="{ fontSize: `${fontPx}px` }"
              >
                {{ line.text }}
              </p>
            </template>
            <p v-else class="text-sm text-muted-foreground">
              {{ loading ? '提取中…' : '本页无文本' }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
