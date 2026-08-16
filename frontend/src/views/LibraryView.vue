<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-vue-next'
import UploadZone from '@/components/papers/UploadZone.vue'
import PaperCard from '@/components/papers/PaperCard.vue'
import { usePapersStore } from '@/stores/papers'
import { fetchPaper, retryParse } from '@/api/papers'

const store = usePapersStore()
const toast = ref('')

onMounted(() => {
  void store.load()
})

async function onUpload(file: File) {
  toast.value = ''
  try {
    await store.upload(file)
    toast.value = `已上传：${file.name}`
  } catch {
    /* store.error 已设置 */
  }
}

async function onRename(id: string, title: string) {
  try {
    await store.rename(id, title)
  } catch (e) {
    store.error = e instanceof Error ? e.message : String(e)
  }
}

async function onRemove(id: string) {
  try {
    await store.remove(id)
  } catch (e) {
    store.error = e instanceof Error ? e.message : String(e)
  }
}

async function onReparse(id: string) {
  try {
    await retryParse(id)
    const paper = await fetchPaper(id)
    const idx = store.items.findIndex((p) => p.id === id)
    if (idx >= 0) store.items[idx] = paper
    else store.items = [paper, ...store.items]
    toast.value = '已重新排队解析（MinerU），完成后状态会变为「已就绪」。'
  } catch (e) {
    store.error = e instanceof Error ? e.message : String(e)
  }
}
</script>

<template>
  <div class="mx-auto max-w-6xl space-y-6 p-4 md:p-6">
    <UploadZone :uploading="store.uploading" @upload="onUpload" />

    <div
      v-if="store.error"
      class="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive"
    >
      <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
      <div class="min-w-0 flex-1">
        <p class="font-medium">操作失败</p>
        <p class="mt-0.5 text-destructive/90">{{ store.error }}</p>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs hover:bg-destructive/10"
        @click="store.load()"
      >
        <RefreshCw class="h-3.5 w-3.5" />
        重试
      </button>
    </div>

    <p
      v-if="toast"
      class="rounded-xl border border-border/60 bg-card/70 px-3 py-2 text-xs text-muted-foreground"
    >
      {{ toast }}
    </p>

    <div class="flex items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold tracking-tight">我的论文</h2>
        <p class="text-xs text-muted-foreground">共 {{ store.items.length }} 篇</p>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-xl border border-border/70 bg-card/70 px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
        :disabled="store.loading"
        @click="store.load()"
      >
        <RefreshCw class="h-3.5 w-3.5" :class="store.loading && 'animate-spin'" />
        刷新
      </button>
    </div>

    <div v-if="store.loading && !store.items.length" class="flex justify-center py-16 text-muted-foreground">
      <Loader2 class="h-6 w-6 animate-spin" />
    </div>

    <div
      v-else-if="!store.items.length"
      class="glass-panel flex flex-col items-center rounded-2xl px-6 py-16 text-center"
    >
      <Inbox class="mb-3 h-10 w-10 text-muted-foreground/70" />
      <p class="text-sm font-medium">还没有论文</p>
      <p class="mt-1 text-xs text-muted-foreground">上传一份 PDF 开始阅读</p>
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <PaperCard
        v-for="paper in store.items"
        :key="paper.id"
        :paper="paper"
        @rename="onRename"
        @remove="onRemove"
        @reparse="onReparse"
      />
    </div>
  </div>
</template>
