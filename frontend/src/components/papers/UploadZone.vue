<script setup lang="ts">
import { ref } from 'vue'
import { UploadCloud, Loader2 } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

defineProps<{
  uploading?: boolean
}>()

const emit = defineEmits<{
  upload: [file: File]
}>()

const dragging = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

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
</script>

<template>
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
      @change="onFiles(($event.target as HTMLInputElement).files); ($event.target as HTMLInputElement).value = ''"
    />
    <div
      class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/12 text-primary"
    >
      <Loader2 v-if="uploading" class="h-6 w-6 animate-spin" />
      <UploadCloud v-else class="h-6 w-6" />
    </div>
    <p class="text-sm font-medium text-foreground">
      {{ uploading ? '正在上传…' : '拖拽 PDF 到此处，或点击选择' }}
    </p>
    <p class="mt-1 max-w-md text-xs text-muted-foreground">
      仅支持含可提取文本的原生 PDF。上传后可立即阅读，结构化解析将在 Milestone 1 接入。
    </p>
  </div>
</template>
