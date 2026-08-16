<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, Library } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

defineProps<{
  collapsed: boolean
  hoverMode?: boolean
}>()

const emit = defineEmits<{
  toggle: []
  navigate: []
}>()

const route = useRoute()
const router = useRouter()

const navItems = [{ label: '论文库', icon: Library, path: '/' }]

function go(path: string) {
  if (route.path !== path) router.push(path)
  emit('navigate')
}
</script>

<template>
  <div class="flex h-full w-full flex-col px-2 py-3" :class="collapsed ? 'items-center' : 'px-3'">
    <div class="mb-4 flex w-full items-center gap-2" :class="collapsed ? 'flex-col gap-2' : 'px-1'">
      <div
        class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm"
      >
        <BookOpen class="h-5 w-5" />
      </div>
      <div v-if="!collapsed" class="min-w-0 flex-1">
        <p class="truncate text-sm font-semibold tracking-tight">PaperLens</p>
        <p class="truncate text-[11px] text-muted-foreground">AI 论文阅读器</p>
      </div>
      <!-- 展开侧栏图标：左边竖线 + 右箭头 -->
      <button
        type="button"
        class="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border/80 text-muted-foreground hover:bg-accent hover:text-foreground"
        :class="!collapsed && 'ml-auto'"
        :aria-label="collapsed ? '展开侧栏' : '收起侧栏'"
        :title="hoverMode ? '悬停展开侧栏' : collapsed ? '展开' : '收起'"
        @click="emit('toggle')"
      >
        <svg
          v-if="collapsed"
          viewBox="0 0 24 24"
          class="h-4 w-4"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M4 5v14" />
          <path d="M10 8l4 4-4 4" />
        </svg>
        <svg
          v-else
          viewBox="0 0 24 24"
          class="h-4 w-4"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M20 5v14" />
          <path d="M14 8l-4 4 4 4" />
        </svg>
      </button>
    </div>

    <nav class="flex w-full flex-col gap-1" :class="collapsed && 'items-center'">
      <button
        v-for="item in navItems"
        :key="item.path"
        type="button"
        :title="item.label"
        :class="
          cn(
            'flex items-center gap-3 rounded-xl py-2.5 text-sm transition-colors',
            collapsed ? 'h-10 w-10 justify-center px-0' : 'px-3',
            route.path === item.path || route.name === 'library'
              ? 'bg-primary/12 font-medium text-primary'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground',
          )
        "
        @click="go(item.path)"
      >
        <component :is="item.icon" class="h-4 w-4 shrink-0" />
        <span v-if="!collapsed">{{ item.label }}</span>
      </button>
    </nav>
  </div>
</template>
