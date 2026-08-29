<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FileText, Pencil, Trash2, ExternalLink, RefreshCw, Loader2 } from 'lucide-vue-next'
import type { Paper } from '@/types'
import { STATUS_LABEL, parseStageLabel } from '@/types'
import { cn, formatBytes, formatDateTime } from '@/lib/utils'

const props = defineProps<{
  paper: Paper
}>()

const emit = defineEmits<{
  rename: [id: string, title: string]
  remove: [id: string]
  reparse: [id: string]
}>()

const router = useRouter()
const editing = ref(false)
const draft = ref('')
const busy = ref(false)

const displayTitle = computed(() => props.paper.title || props.paper.filename)
const showProgress = computed(() => ['queued', 'parsing'].includes(props.paper.status))
const progressPct = computed(() => {
  const p = props.paper.parse_progress
  if (typeof p === 'number' && p >= 0) return Math.min(100, Math.max(0, p))
  if (props.paper.status === 'queued') return 2
  if (props.paper.status === 'parsing') return 12
  return 0
})
const progressHint = computed(() => {
  const stage = parseStageLabel(props.paper.parse_stage)
  if (stage) return `${stage} · ${progressPct.value}%`
  return props.paper.status === 'queued' ? '排队等待…' : '解析中…'
})

function open() {
  router.push({ name: 'reader', params: { id: props.paper.id } })
}

function startEdit() {
  draft.value = displayTitle.value
  editing.value = true
}

async function commitEdit() {
  const next = draft.value.trim()
  if (!next || next === displayTitle.value) {
    editing.value = false
    return
  }
  busy.value = true
  try {
    emit('rename', props.paper.id, next)
    editing.value = false
  } finally {
    busy.value = false
  }
}

function confirmRemove() {
  if (window.confirm(`确定删除「${displayTitle.value}」？将移除本地 PDF 及关联记录。`)) {
    emit('remove', props.paper.id)
  }
}

function confirmReparse() {
  if (['queued', 'parsing'].includes(props.paper.status)) return
  if (
    window.confirm(
      `用当前解析器（MinerU）重新解析「${displayTitle.value}」？现有版式会被覆盖，可能需要几分钟。`,
    )
  ) {
    emit('reparse', props.paper.id)
  }
}
</script>

<template>
  <article
    class="glass-panel group flex flex-col rounded-2xl p-4 transition hover:-translate-y-0.5 hover:shadow-lg"
  >
    <div class="mb-3 flex items-start gap-3">
      <div
        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary"
      >
        <FileText class="h-5 w-5" />
      </div>
      <div class="min-w-0 flex-1">
        <div v-if="editing" class="flex min-w-0 items-center gap-2">
          <input
            v-model="draft"
            class="min-w-0 flex-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm outline-none ring-primary focus:ring-2"
            @keydown.enter="commitEdit"
            @keydown.esc="editing = false"
          />
          <button
            type="button"
            class="inline-flex h-8 shrink-0 items-center justify-center whitespace-nowrap rounded-lg bg-primary px-3 text-xs text-primary-foreground"
            :disabled="busy"
            @click="commitEdit"
          >
            保存
          </button>
        </div>
        <h3 v-else class="line-clamp-2 text-sm font-semibold leading-snug text-foreground">
          {{ displayTitle }}
        </h3>
        <p class="mt-1 truncate text-xs text-muted-foreground">{{ paper.filename }}</p>
      </div>
    </div>

    <div class="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span :class="cn('status-pill inline-flex items-center gap-1', `status-${paper.status}`)">
        <Loader2
          v-if="paper.status === 'queued' || paper.status === 'parsing'"
          class="h-3 w-3 animate-spin"
        />
        {{ STATUS_LABEL[paper.status] }}
      </span>
      <span v-if="paper.page_count">{{ paper.page_count }} 页</span>
      <span>{{ formatBytes(paper.file_size) }}</span>
      <span>{{ formatDateTime(paper.created_at) }}</span>
    </div>

    <div v-if="showProgress" class="mb-3 space-y-1.5">
      <div class="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span class="truncate">{{ progressHint }}</span>
        <span class="shrink-0 tabular-nums">{{ progressPct }}%</span>
      </div>
      <div class="h-1.5 overflow-hidden rounded-full bg-border/70">
        <div
          class="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
          :style="{ width: `${progressPct}%` }"
        />
      </div>
    </div>

    <p v-if="paper.error_message" class="mb-3 text-xs text-destructive">
      {{ paper.error_message }}
    </p>

    <div class="mt-auto flex items-center gap-2">
      <button
        type="button"
        class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        @click="open"
      >
        <ExternalLink class="h-4 w-4" />
        打开
      </button>
      <button
        type="button"
        class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border/80 bg-card/80 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40"
        title="重新用 MinerU 解析"
        :disabled="['queued', 'parsing'].includes(paper.status)"
        @click="confirmReparse"
      >
        <RefreshCw class="h-4 w-4" />
      </button>
      <button
        type="button"
        class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border/80 bg-card/80 text-muted-foreground hover:bg-accent hover:text-foreground"
        title="重命名"
        @click="startEdit"
      >
        <Pencil class="h-4 w-4" />
      </button>
      <button
        type="button"
        class="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border/80 bg-card/80 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
        title="删除"
        @click="confirmRemove"
      >
        <Trash2 class="h-4 w-4" />
      </button>
    </div>
  </article>
</template>
