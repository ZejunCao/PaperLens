<script setup lang="ts">
import { computed } from 'vue'
import {
  ArchiveRestore,
  FileText,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
} from 'lucide-vue-next'
import type { Paper } from '@/types'
import { STATUS_LABEL, parseStageLabel } from '@/types'
import { cn, formatDateTime } from '@/lib/utils'

const props = defineProps<{
  paper: Paper
  selected?: boolean
  folderName?: string
  trash?: boolean
}>()

const emit = defineEmits<{
  select: [id: string, selected: boolean]
  open: [id: string]
  rename: [id: string]
  remove: [id: string]
  restore: [id: string]
  permanent: [id: string]
  reparse: [id: string]
}>()

const displayTitle = computed(() => props.paper.title || props.paper.filename)
const progress = computed(() => Math.min(100, Math.max(0, props.paper.parse_progress || 0)))
const active = computed(() => ['queued', 'parsing'].includes(props.paper.status))

function startDrag(event: DragEvent) {
  event.dataTransfer?.setData('application/x-paperlens-paper', props.paper.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
</script>

<template>
  <article
    class="group grid min-h-[66px] cursor-default grid-cols-[34px_minmax(240px,1fr)_120px_90px_128px_116px] items-center gap-3 border-t border-border/45 px-3 transition-colors first:border-t-0 hover:bg-white/45"
    :class="selected && 'bg-primary/6'"
    draggable="true"
    @dragstart="startDrag"
    @dblclick="!trash && emit('open', paper.id)"
  >
    <label class="grid h-8 w-8 cursor-pointer place-items-center" @dblclick.stop>
      <input
        type="checkbox"
        class="h-3.5 w-3.5 accent-primary"
        :checked="selected"
        :aria-label="`选择 ${displayTitle}`"
        @change="emit('select', paper.id, ($event.target as HTMLInputElement).checked)"
      />
    </label>
    <div class="flex min-w-0 items-center gap-3">
      <div class="grid h-10 w-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
        <FileText class="h-4 w-4" />
      </div>
      <div class="min-w-0">
        <p class="truncate text-sm font-medium text-foreground" :title="displayTitle">{{ displayTitle }}</p>
        <p class="mt-0.5 truncate text-[10px] text-muted-foreground">
          {{ folderName || '未归档' }} · {{ paper.filename }}
        </p>
      </div>
    </div>
    <div class="min-w-0">
      <span :class="cn('status-pill', `status-${paper.status}`)">
        <Loader2 v-if="active" class="h-3 w-3 animate-spin" />
        {{ STATUS_LABEL[paper.status] }}
      </span>
      <div v-if="active" class="mt-1.5 h-1 w-20 overflow-hidden rounded-full bg-border/70">
        <div class="h-full rounded-full bg-primary" :style="{ width: `${progress || 3}%` }" />
      </div>
      <p v-if="paper.status === 'failed'" class="mt-1 truncate text-[10px] text-destructive" :title="paper.error_message || ''">
        {{ paper.error_message || '解析失败' }}
      </p>
    </div>
    <span class="text-xs tabular-nums text-muted-foreground">{{ paper.page_count ? `${paper.page_count} 页` : '—' }}</span>
    <span class="text-xs tabular-nums text-muted-foreground">{{ formatDateTime(paper.updated_at) }}</span>
    <div class="flex items-center justify-end gap-0.5 opacity-55 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
      <template v-if="trash">
        <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground" title="恢复" @click="emit('restore', paper.id)">
          <ArchiveRestore class="h-4 w-4" />
        </button>
        <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive" title="永久删除" @click="emit('permanent', paper.id)">
          <Trash2 class="h-4 w-4" />
        </button>
      </template>
      <template v-else>
        <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30" :disabled="active" :title="active ? parseStageLabel(paper.parse_stage) : '重新解析'" @click="emit('reparse', paper.id)">
          <RefreshCw class="h-4 w-4" />
        </button>
        <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground" title="重命名" @click="emit('rename', paper.id)">
          <Pencil class="h-4 w-4" />
        </button>
        <button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive" title="移到回收站" @click="emit('remove', paper.id)">
          <Trash2 class="h-4 w-4" />
        </button>
      </template>
    </div>
  </article>
</template>
