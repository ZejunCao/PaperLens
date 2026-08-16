<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Menu } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useUiStore } from '@/stores/ui'
import { cn } from '@/lib/utils'

const ui = useUiStore()
const route = useRoute()
const mobileOpen = ref(false)
const sidebarHover = ref(false)

const isReader = computed(() => route.name === 'reader')
const headerTitle = computed(() => (route.name === 'settings' ? '设置' : '论文库'))
const headerSub = computed(() =>
  route.name === 'settings' ? 'OpenAI 兼容接口与模型' : '上传、管理并打开本地论文',
)
const sidebarExpanded = computed(() => sidebarHover.value)

onMounted(() => {
  ui.initTheme()
})
</script>

<template>
  <div class="app-shell flex h-screen overflow-hidden">
    <div v-if="!isReader" class="app-shell__mesh" aria-hidden="true" />

    <aside
      class="relative z-30 hidden h-full w-14 shrink-0 overflow-visible md:flex"
    >
      <div
        class="absolute inset-y-0 left-0 z-40 flex border-r border-border/60 bg-[#f7f3ec] shadow-sm transition-[width] duration-200 ease-out"
        :class="sidebarExpanded ? 'w-[220px] shadow-lg' : 'w-14'"
        @mouseenter="sidebarHover = true"
        @mouseleave="sidebarHover = false"
      >
        <AppSidebar
          :collapsed="!sidebarExpanded"
          :hover-mode="true"
          @toggle="sidebarHover = !sidebarHover"
        />
      </div>
    </aside>

    <div
      v-if="mobileOpen"
      class="fixed inset-0 z-40 bg-black/20 md:hidden"
      @click="mobileOpen = false"
    />
    <aside
      class="fixed inset-y-0 left-0 z-50 flex w-[220px] border-r border-border/60 bg-[#f7f3ec] transition-transform md:hidden"
      :class="mobileOpen ? 'translate-x-0' : '-translate-x-full'"
    >
      <AppSidebar :collapsed="false" @toggle="mobileOpen = false" @navigate="mobileOpen = false" />
    </aside>

    <div class="relative z-10 flex min-w-0 flex-1 flex-col">
      <header
        v-if="!isReader"
        class="flex h-14 items-center justify-between gap-3 border-b border-border/50 bg-[#f7f3ec]/90 px-4"
      >
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/70 md:hidden"
            aria-label="打开菜单"
            @click="mobileOpen = true"
          >
            <Menu class="h-5 w-5" />
          </button>
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold tracking-tight">{{ headerTitle }}</p>
            <p class="truncate text-xs text-muted-foreground">{{ headerSub }}</p>
          </div>
        </div>
      </header>

      <div
        v-else
        class="flex h-11 items-center gap-2 border-b border-border/40 bg-[#f7f3ec] px-2 md:hidden"
      >
        <button
          type="button"
          class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/70"
          @click="mobileOpen = true"
        >
          <Menu class="h-4 w-4" />
        </button>
        <span class="text-xs text-muted-foreground">PaperLens</span>
      </div>

      <main :class="cn('min-h-0 flex-1', isReader ? 'overflow-hidden' : 'overflow-auto')">
        <RouterView />
      </main>
    </div>
  </div>
</template>
