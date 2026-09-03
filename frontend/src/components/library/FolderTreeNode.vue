<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ChevronDown, ChevronRight, Folder, FolderPlus, MoreHorizontal } from 'lucide-vue-next'
import type { FolderNode } from '@/stores/folders'

defineOptions({ name: 'FolderTreeNode' })

const props = defineProps<{
  node: FolderNode
  selectedId: string | null
  depth?: number
}>()

const emit = defineEmits<{
  select: [id: string]
  createChild: [id: string]
  rename: [id: string]
  remove: [id: string]
  dropPaper: [paperId: string, folderId: string]
}>()

const expanded = ref(true)
const menuOpen = ref(false)
const dragOver = ref(false)
const menuRoot = ref<HTMLElement | null>(null)

function closeMenuOutside(event: PointerEvent) {
  if (menuOpen.value && !menuRoot.value?.contains(event.target as Node)) menuOpen.value = false
}

function closeMenuWithKeyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') menuOpen.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', closeMenuOutside)
  document.addEventListener('keydown', closeMenuWithKeyboard)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeMenuOutside)
  document.removeEventListener('keydown', closeMenuWithKeyboard)
})

function onDrop(event: DragEvent) {
  dragOver.value = false
  const paperId = event.dataTransfer?.getData('application/x-paperlens-paper') || ''
  if (paperId) emit('dropPaper', paperId, props.node.id)
}
</script>

<template>
  <div>
    <div
      ref="menuRoot"
      class="group relative flex h-9 cursor-pointer items-center gap-1 rounded-xl pr-1 text-sm transition-colors"
      :class="[
        selectedId === node.id
          ? 'bg-primary/12 font-medium text-primary'
          : 'text-muted-foreground hover:bg-white/45 hover:text-foreground',
        dragOver && 'ring-2 ring-primary/45',
      ]"
      :style="{ paddingLeft: `${8 + (depth || 0) * 16}px` }"
      @click="emit('select', node.id)"
      @dragenter.prevent="dragOver = true"
      @dragover.prevent
      @dragleave.self="dragOver = false"
      @drop.prevent="onDrop"
    >
      <button
        type="button"
        class="grid h-6 w-5 shrink-0 place-items-center rounded-md hover:bg-black/5"
        :class="!node.children.length && 'invisible'"
        :aria-label="expanded ? '折叠文件夹' : '展开文件夹'"
        @click.stop="expanded = !expanded"
      >
        <ChevronDown v-if="expanded" class="h-3.5 w-3.5" />
        <ChevronRight v-else class="h-3.5 w-3.5" />
      </button>
      <Folder class="h-4 w-4 shrink-0" />
      <span class="min-w-0 flex-1 truncate">{{ node.name }}</span>
      <span class="text-[10px] tabular-nums text-muted-foreground/65">{{ node.paper_count }}</span>
      <button
        type="button"
        class="grid h-7 w-7 shrink-0 place-items-center rounded-lg opacity-0 hover:bg-black/5 group-hover:opacity-100"
        aria-label="文件夹操作"
        :aria-expanded="menuOpen"
        @click.stop="menuOpen = !menuOpen"
      >
        <MoreHorizontal class="h-3.5 w-3.5" />
      </button>
      <div
        v-if="menuOpen"
        class="absolute right-1 top-8 z-20 w-32 rounded-xl border border-border/70 bg-[#fffdf9] p-1 text-xs text-foreground shadow-xl"
        @click.stop
      >
        <button
          type="button"
          class="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-accent"
          @click="menuOpen = false; emit('createChild', node.id)"
        >
          <FolderPlus class="h-3.5 w-3.5" /> 新建子文件夹
        </button>
        <button
          type="button"
          class="w-full rounded-lg px-2.5 py-2 text-left hover:bg-accent"
          @click="menuOpen = false; emit('rename', node.id)"
        >
          重命名
        </button>
        <button
          type="button"
          class="w-full rounded-lg px-2.5 py-2 text-left text-destructive hover:bg-destructive/8"
          @click="menuOpen = false; emit('remove', node.id)"
        >
          删除文件夹
        </button>
      </div>
    </div>
    <div v-if="expanded && node.children.length">
      <FolderTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :selected-id="selectedId"
        :depth="(depth || 0) + 1"
        @select="emit('select', $event)"
        @create-child="emit('createChild', $event)"
        @rename="emit('rename', $event)"
        @remove="emit('remove', $event)"
        @drop-paper="(paperId, folderId) => emit('dropPaper', paperId, folderId)"
      />
    </div>
  </div>
</template>
