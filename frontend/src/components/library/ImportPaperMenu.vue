<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ChevronDown, FileUp, Link2, Loader2, Plus } from 'lucide-vue-next'

defineProps<{ uploading?: boolean; destination?: string }>()

const emit = defineEmits<{
  upload: [file: File]
  importUrl: [url: string]
}>()

const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const open = ref(false)
const url = ref('')

function closeOutside(event: MouseEvent) {
  if (!root.value?.contains(event.target as Node)) open.value = false
}

function closeWithKeyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

function chooseFile(files: FileList | null) {
  const file = files?.[0]
  if (!file) return
  emit('upload', file)
  open.value = false
}

function submitUrl() {
  const value = url.value.trim()
  if (!value) return
  emit('importUrl', value)
  url.value = ''
  open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', closeOutside)
  document.addEventListener('keydown', closeWithKeyboard)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOutside)
  document.removeEventListener('keydown', closeWithKeyboard)
})
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      class="inline-flex h-9 items-center gap-1.5 rounded-xl bg-primary px-3.5 text-xs font-medium text-primary-foreground shadow-sm transition hover:opacity-90 disabled:opacity-60"
      :disabled="uploading"
      :aria-expanded="open"
      @click="open = !open"
    >
      <Loader2 v-if="uploading" class="h-3.5 w-3.5 animate-spin" />
      <Plus v-else class="h-3.5 w-3.5" />
      {{ uploading ? '正在导入' : '导入论文' }}
      <ChevronDown class="h-3 w-3" />
    </button>
    <div
      v-if="open"
      class="absolute right-0 top-11 z-30 w-[330px] rounded-2xl border border-border/70 bg-[#fffdf9] p-3 shadow-2xl"
      @pointerdown.stop
    >
      <p class="px-1 text-xs font-medium">导入到 {{ destination || '未归档' }}</p>
      <p class="mb-3 mt-0.5 px-1 text-[10px] text-muted-foreground">论文只保存在一个文件夹中，可随时拖动调整。</p>
      <input
        ref="input"
        type="file"
        accept="application/pdf,.pdf"
        class="hidden"
        @change="chooseFile(($event.target as HTMLInputElement).files); ($event.target as HTMLInputElement).value = ''"
      />
      <button
        type="button"
        class="flex w-full items-center gap-3 rounded-xl border border-border/65 bg-white/50 px-3 py-2.5 text-left text-xs hover:bg-accent"
        @click="input?.click()"
      >
        <span class="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary"><FileUp class="h-4 w-4" /></span>
        <span><b class="block font-medium">选择本地 PDF</b><small class="text-[10px] text-muted-foreground">上传后自动开始解析</small></span>
      </button>
      <div class="mt-2 flex items-center gap-2 rounded-xl border border-border/65 bg-white/50 p-2">
        <Link2 class="ml-1 h-4 w-4 shrink-0 text-muted-foreground" />
        <input
          v-model="url"
          class="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground/65"
          placeholder="粘贴 arXiv 链接或 ID"
          @keydown.enter.prevent="submitUrl"
        />
        <button
          type="button"
          class="rounded-lg bg-primary px-2.5 py-1.5 text-[10px] font-medium text-primary-foreground disabled:opacity-40"
          :disabled="!url.trim()"
          @click="submitUrl"
        >
          导入
        </button>
      </div>
    </div>
  </div>
</template>
