<script setup lang="ts">
import {
  Columns2,
  Highlighter,
  Languages,
  MessageSquare,
  Quote,
  Search,
  Sparkles,
} from 'lucide-vue-next'

/** 右侧功能轨：先占位，后续里程碑再接线 */
const placeholders = [
  { icon: Columns2, label: '阅读布局' },
  { icon: Languages, label: '翻译' },
  { icon: Highlighter, label: '高亮' },
  { icon: Search, label: '检索' },
  { icon: MessageSquare, label: 'AI 问答' },
  { icon: Quote, label: '引用' },
  { icon: Sparkles, label: '概要' },
]
</script>

<template>
  <aside
    class="flex w-12 shrink-0 flex-col items-center gap-1 border-l border-border/60 bg-[#f7f3ec] py-3"
    aria-label="阅读工具（预留）"
  >
    <button
      v-for="item in placeholders"
      :key="item.label"
      type="button"
      class="inline-flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground/55"
      :title="`${item.label}（即将推出）`"
      disabled
    >
      <component :is="item.icon" class="h-4 w-4" />
    </button>
  </aside>
</template>
