<script setup lang="ts">
import { computed } from 'vue'
import { BookOpen, ExternalLink, FileText, Loader2, RefreshCw, X } from 'lucide-vue-next'
import type { Paper } from '@/types'

const props = defineProps<{ paper: Paper; refreshing?: boolean }>()
const emit = defineEmits<{ close: []; open: [id: string]; refresh: [id: string] }>()

const publishedDate = computed(() => props.paper.published_at
  ? new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }).format(new Date(props.paper.published_at))
  : '')
</script>

<template>
  <aside class="flex h-full min-h-0 flex-col border-l border-border/55 bg-[#fffdf9]/95 shadow-[-10px_0_30px_rgba(48,35,24,0.04)]">
    <header class="flex h-14 shrink-0 items-center justify-between border-b border-border/50 px-4">
      <div class="flex min-w-0 items-center gap-2 text-xs font-medium"><FileText class="h-4 w-4 text-primary" />论文详情</div>
      <div class="flex items-center gap-1"><button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50" title="重新获取元信息" :disabled="refreshing" @click="emit('refresh', paper.id)"><Loader2 v-if="refreshing" class="h-4 w-4 animate-spin" /><RefreshCw v-else class="h-4 w-4" /></button><button type="button" class="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground" aria-label="关闭详情" @click="emit('close')"><X class="h-4 w-4" /></button></div>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
      <div class="grid grid-cols-[64px_minmax(0,1fr)] gap-x-4 gap-y-4 text-xs leading-5">
        <span class="text-muted-foreground">作者</span>
        <span>{{ paper.authors.length ? paper.authors.join('、') : '暂未获取' }}</span>
        <span class="text-muted-foreground">机构</span>
        <span>{{ paper.institutions.length ? paper.institutions.join('、') : '暂未获取' }}</span>
        <span class="text-muted-foreground">期刊/会议</span><span>{{ paper.publication || '暂未获取' }}</span>
        <span class="text-muted-foreground">发表时间</span><span>{{ publishedDate || '暂未获取' }}</span>
      </div>

      <section v-if="paper.abstract" class="mt-6 border-t border-border/50 pt-5">
        <h3 class="text-xs font-semibold">摘要</h3>
        <p class="mt-2 whitespace-pre-line text-xs leading-5 text-muted-foreground">{{ paper.abstract }}</p>
      </section>

      <p v-if="!paper.authors.length && !paper.institutions.length && !paper.publication && !paper.abstract" class="mt-8 rounded-xl bg-muted/35 px-3 py-3 text-xs leading-5 text-muted-foreground">当前文件没有可识别的学术元信息，可以点击顶部刷新按钮重新获取。</p>
    </div>

    <footer class="grid shrink-0 grid-cols-[1fr_auto] gap-2 border-t border-border/50 p-4">
      <button type="button" class="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-primary text-xs font-medium text-primary-foreground disabled:opacity-50" :disabled="paper.status !== 'ready'" @click="emit('open', paper.id)"><BookOpen class="h-4 w-4" />打开阅读</button>
      <a v-if="paper.source_url" :href="paper.source_url" target="_blank" rel="noreferrer" class="grid h-10 w-10 place-items-center rounded-xl border border-border/70 text-muted-foreground hover:bg-accent" title="打开来源"><ExternalLink class="h-4 w-4" /></a>
    </footer>
  </aside>
</template>
