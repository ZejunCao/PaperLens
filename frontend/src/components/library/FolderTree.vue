<script setup lang="ts">
import { Clock3, FileQuestion, FolderPlus, Inbox, Trash2 } from 'lucide-vue-next'
import FolderTreeNode from '@/components/library/FolderTreeNode.vue'
import type { LibraryView } from '@/types'
import type { FolderNode } from '@/stores/folders'

defineProps<{
  tree: FolderNode[]
  selectedView: LibraryView
  selectedFolderId: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  selectView: [view: LibraryView]
  selectFolder: [id: string]
  createRoot: []
  createChild: [id: string]
  rename: [id: string]
  remove: [id: string]
  dropPaper: [paperId: string, folderId: string | null]
}>()

const quick = [
  { id: 'all' as const, label: '全部论文', icon: Inbox },
  { id: 'recent' as const, label: '最近阅读', icon: Clock3 },
  { id: 'unfiled' as const, label: '未归档', icon: FileQuestion },
]

function dropUnfiled(event: DragEvent) {
  const paperId = event.dataTransfer?.getData('application/x-paperlens-paper') || ''
  if (paperId) emit('dropPaper', paperId, null)
}
</script>

<template>
  <aside class="flex h-full min-h-0 flex-col px-3 py-4">
    <p class="px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/70">
      快捷入口
    </p>
    <nav class="mt-2 space-y-1">
      <button
        v-for="item in quick"
        :key="item.id"
        type="button"
        class="flex h-9 w-full items-center gap-2.5 rounded-xl px-3 text-sm transition-colors"
        :class="!selectedFolderId && selectedView === item.id ? 'bg-primary/12 font-medium text-primary' : 'text-muted-foreground hover:bg-white/45 hover:text-foreground'"
        @click="emit('selectView', item.id)"
        @dragover.prevent="item.id === 'unfiled'"
        @drop.prevent="item.id === 'unfiled' && dropUnfiled($event)"
      >
        <component :is="item.icon" class="h-4 w-4" />
        {{ item.label }}
      </button>
    </nav>

    <div class="my-4 h-px bg-border/55" />
    <div class="mb-2 flex items-center justify-between px-2">
      <p class="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/70">我的文件夹</p>
      <button
        type="button"
        class="grid h-7 w-7 place-items-center rounded-lg text-primary hover:bg-primary/10"
        title="新建文件夹"
        @click="emit('createRoot')"
      >
        <FolderPlus class="h-4 w-4" />
      </button>
    </div>
    <div class="min-h-0 flex-1 overflow-y-auto">
      <p v-if="loading && !tree.length" class="px-3 py-5 text-xs text-muted-foreground">正在加载目录…</p>
      <p v-else-if="!tree.length" class="px-3 py-5 text-xs leading-5 text-muted-foreground">
        暂无文件夹，点击右上角创建。
      </p>
      <FolderTreeNode
        v-for="node in tree"
        :key="node.id"
        :node="node"
        :selected-id="selectedFolderId"
        @select="emit('selectFolder', $event)"
        @create-child="emit('createChild', $event)"
        @rename="emit('rename', $event)"
        @remove="emit('remove', $event)"
        @drop-paper="(paperId, folderId) => emit('dropPaper', paperId, folderId)"
      />
    </div>

    <div class="mt-3 border-t border-border/55 pt-3">
      <button
        type="button"
        class="flex h-9 w-full items-center gap-2.5 rounded-xl px-3 text-sm transition-colors"
        :class="!selectedFolderId && selectedView === 'trash' ? 'bg-primary/12 font-medium text-primary' : 'text-muted-foreground hover:bg-white/45 hover:text-foreground'"
        @click="emit('selectView', 'trash')"
      >
        <Trash2 class="h-4 w-4" /> 回收站
      </button>
    </div>
  </aside>
</template>
