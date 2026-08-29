<script setup lang="ts">
import { ref } from 'vue'
import { UploadCloud, Loader2, Link2 } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

defineProps<{
  uploading?: boolean
}>()

const emit = defineEmits<{
  upload: [file: File]
  importUrl: [url: string]
}>()

const dragging = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)
const arxivUrl = ref('')

function pick() {
  inputRef.value?.click()
}

function onFiles(files: FileList | null) {
  const file = files?.[0]
  if (!file) return
  emit('upload', file)
}

function onDrop(e: DragEvent) {
  dragging.value = false
  onFiles(e.dataTransfer?.files ?? null)
}

function onImportArxiv() {
  const url = arxivUrl.value.trim()
  if (!url) return
  emit('importUrl', url)
}

function onArxivKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    onImportArxiv()
  }
}
</script>

<template>
  <div class="space-y-3">
    <div
      :class="
        cn(
          'glass-panel relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-border/80 px-6 py-10 text-center transition',
          dragging && 'border-primary bg-primary/5',
          uploading && 'pointer-events-none opacity-70',
        )
      "
      @click="pick"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <input
        ref="inputRef"
        type="file"
        accept="application/pdf,.pdf"
        class="hidden"
        @change="
          onFiles(($event.target as HTMLInputElement).files);
          ($event.target as HTMLInputElement).value = ''
        "
      />
      <div
        class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/12 text-primary"
      >
        <Loader2 v-if="uploading" class="h-6 w-6 animate-spin" />
        <UploadCloud v-else class="h-6 w-6" />
      </div>
      <p class="text-sm font-medium text-foreground">
        {{ uploading ? '正在导入…' : '拖拽 PDF 到此处，或点击选择' }}
      </p>
      <p class="mt-1 max-w-md text-xs text-muted-foreground">
        仅支持含可提取文本的原生 PDF。上传后会本地下载/落盘并自动排队解析。
      </p>
    </div>

    <div
      :class="
        cn(
          'glass-panel flex flex-col gap-2 rounded-2xl border border-border/70 px-4 py-3 sm:flex-row sm:items-center',
          uploading && 'pointer-events-none opacity-70',
        )
      "
      @click.stop
    >
      <div class="flex min-w-0 flex-1 items-center gap-2">
        <Link2 class="h-4 w-4 shrink-0 text-muted-foreground" />
        <input
          v-model="arxivUrl"
          type="text"
          placeholder="粘贴 arXiv 链接或 ID，例如 https://arxiv.org/abs/2301.07041"
          class="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/70"
          :disabled="uploading"
          @keydown="onArxivKeydown"
          @click.stop
        />
      </div>
      <button
        type="button"
        class="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        :disabled="uploading || !arxivUrl.trim()"
        @click.stop="onImportArxiv"
      >
        <Loader2 v-if="uploading" class="h-3.5 w-3.5 animate-spin" />
        从 arXiv 导入
      </button>
    </div>
  </div>
</template>
