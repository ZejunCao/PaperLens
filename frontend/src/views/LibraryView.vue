<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertCircle,
  CheckSquare,
  FolderInput,
  Inbox,
  Loader2,
  Menu,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-vue-next'
import FolderTree from '@/components/library/FolderTree.vue'
import FolderDialog from '@/components/library/FolderDialog.vue'
import ImportPaperMenu from '@/components/library/ImportPaperMenu.vue'
import PaperListRow from '@/components/library/PaperListRow.vue'
import { useFoldersStore } from '@/stores/folders'
import { usePapersStore } from '@/stores/papers'
import * as papersApi from '@/api/papers'
import type { LibraryView, PaperSort } from '@/types'

const papers = usePapersStore()
const folders = useFoldersStore()
const route = useRoute()
const router = useRouter()

const validViews = new Set<LibraryView>(['all', 'unfiled', 'recent', 'trash'])
const initialView = typeof route.query.view === 'string' && validViews.has(route.query.view as LibraryView)
  ? route.query.view as LibraryView
  : 'all'

const selectedView = ref<LibraryView>(initialView)
const selectedFolderId = ref(typeof route.query.folder === 'string' ? route.query.folder : null)
const query = ref('')
const sort = ref<PaperSort>('updated')
const selected = ref<Set<string>>(new Set())
const toast = ref('')
const folderPanelOpen = ref(false)
const draggingFile = ref(false)
const folderEditor = ref<{
  mode: 'create' | 'rename'
  parentId: string | null
  folderId: string | null
  title: string
  value: string
} | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

const folderMap = computed(() => new Map(folders.items.map((folder) => [folder.id, folder])))
const currentFolder = computed(() => selectedFolderId.value ? folderMap.value.get(selectedFolderId.value) : undefined)
const currentTitle = computed(() => {
  if (currentFolder.value) return currentFolder.value.name
  return {
    all: '全部论文',
    recent: '最近阅读',
    processing: '正在解析',
    unfiled: '未归档',
    trash: '回收站',
  }[selectedView.value]
})
const currentPath = computed(() => {
  const names: string[] = []
  let folder = currentFolder.value
  const seen = new Set<string>()
  while (folder && !seen.has(folder.id)) {
    seen.add(folder.id)
    names.unshift(folder.name)
    folder = folder.parent_id ? folderMap.value.get(folder.parent_id) : undefined
  }
  return names.join(' / ')
})
const allSelected = computed(() => papers.items.length > 0 && selected.value.size === papers.items.length)
const error = computed(() => papers.error || folders.error)

function paperQuery() {
  return {
    folderId: selectedFolderId.value,
    view: selectedFolderId.value ? 'all' as const : selectedView.value,
    query: query.value,
    sort: sort.value,
  }
}

async function loadPapers() {
  selected.value = new Set()
  await papers.load(paperQuery())
}

async function refreshAll() {
  await Promise.all([folders.load(), loadPapers()])
}

function syncRoute() {
  const next: Record<string, string> = {}
  if (selectedFolderId.value) next.folder = selectedFolderId.value
  else if (selectedView.value !== 'all') next.view = selectedView.value
  void router.replace({ query: next })
}

function selectView(view: LibraryView) {
  selectedFolderId.value = null
  selectedView.value = view
  folderPanelOpen.value = false
  syncRoute()
  void loadPapers()
}

function selectFolder(id: string) {
  selectedFolderId.value = id
  selectedView.value = 'all'
  folderPanelOpen.value = false
  syncRoute()
  void loadPapers()
}

function createFolder(parentId: string | null = null) {
  folderEditor.value = {
    mode: 'create',
    parentId,
    folderId: null,
    title: parentId ? '新建子文件夹' : '新建文件夹',
    value: '',
  }
}

function renameFolder(id: string) {
  const folder = folderMap.value.get(id)
  if (!folder) return
  folderEditor.value = {
    mode: 'rename',
    parentId: folder.parent_id,
    folderId: id,
    title: '重命名文件夹',
    value: folder.name,
  }
}

async function saveFolder(name: string) {
  const editor = folderEditor.value
  if (!editor) return
  try {
    if (editor.mode === 'create') {
      const folder = await folders.create(name, editor.parentId)
      toast.value = `已创建文件夹「${folder.name}」`
    } else if (editor.folderId) {
      await folders.rename(editor.folderId, name)
    }
    folderEditor.value = null
  } catch (e) {
    papers.error = e instanceof Error ? e.message : String(e)
  }
}

async function removeFolder(id: string) {
  const folder = folderMap.value.get(id)
  if (!folder || !window.confirm(`删除文件夹「${folder.name}」？其中论文会移到“未归档”，子文件夹会提升一级。`)) return
  try {
    await folders.remove(id)
    if (selectedFolderId.value === id) selectView('unfiled')
    else await loadPapers()
    toast.value = `已删除文件夹「${folder.name}」`
  } catch (e) {
    papers.error = e instanceof Error ? e.message : String(e)
  }
}

async function movePaper(paperId: string, folderId: string | null) {
  try {
    await papersApi.movePaper(paperId, folderId)
    const targetName = folderId ? folderMap.value.get(folderId)?.name || '目标文件夹' : '未归档'
    await refreshAll()
    toast.value = `已移动到「${targetName}」`
  } catch (e) {
    papers.error = e instanceof Error ? e.message : String(e)
  }
}

async function upload(file: File) {
  try {
    const paper = await papers.upload(file, selectedFolderId.value)
    await refreshAll()
    toast.value = `已导入「${paper.title || paper.filename}」`
  } catch {
    /* store 已记录错误 */
  }
}

async function importUrl(url: string) {
  try {
    const paper = await papers.importFromUrl(url, selectedFolderId.value)
    await refreshAll()
    toast.value = `已导入「${paper.title || paper.filename}」`
  } catch {
    /* store 已记录错误 */
  }
}

function openPaper(id: string) {
  void router.push({ name: 'reader', params: { id } })
}

async function renamePaper(id: string) {
  const paper = papers.items.find((item) => item.id === id)
  if (!paper) return
  const title = window.prompt('重命名论文', paper.title || paper.filename)?.trim()
  if (!title) return
  try {
    await papers.rename(id, title)
  } catch (e) {
    papers.error = e instanceof Error ? e.message : String(e)
  }
}

async function trashPaper(id: string) {
  const paper = papers.items.find((item) => item.id === id)
  if (!paper || !window.confirm(`将「${paper.title || paper.filename}」移到回收站？`)) return
  await papers.remove(id)
  await folders.load()
}

async function restorePaper(id: string) {
  await papers.restore(id)
  await folders.load()
  toast.value = '论文已恢复'
}

async function permanentPaper(id: string) {
  const paper = papers.items.find((item) => item.id === id)
  if (!paper || !window.confirm(`永久删除「${paper.title || paper.filename}」？PDF 与解析数据将无法恢复。`)) return
  await papers.removePermanently(id)
}

async function reparsePaper(id: string) {
  const paper = papers.items.find((item) => item.id === id)
  if (!paper || !window.confirm(`重新解析「${paper.title || paper.filename}」？`)) return
  await papers.reparse(id)
}

function toggleSelected(id: string, checked: boolean) {
  const next = new Set(selected.value)
  if (checked) next.add(id)
  else next.delete(id)
  selected.value = next
}

function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(papers.items.map((paper) => paper.id))
}

async function moveSelected(event: Event) {
  const element = event.target as HTMLSelectElement
  const value = element.value
  if (!value) return
  const count = selected.value.size
  const folderId = value === '__unfiled__' ? null : value
  await Promise.all([...selected.value].map((id) => papersApi.movePaper(id, folderId)))
  await refreshAll()
  toast.value = `已移动 ${count} 篇论文`
  element.value = ''
}

async function trashSelected() {
  if (!selected.value.size || !window.confirm(`将选中的 ${selected.value.size} 篇论文移到回收站？`)) return
  await Promise.all([...selected.value].map((id) => papersApi.deletePaper(id)))
  await refreshAll()
}

function onFileDrop(event: DragEvent) {
  draggingFile.value = false
  const files = [...(event.dataTransfer?.files || [])]
  const pdf = files.find((file) => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'))
  if (pdf) void upload(pdf)
}

function closeTransientLayer(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    folderPanelOpen.value = false
    draggingFile.value = false
  }
}

watch(query, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void loadPapers(), 250)
})
watch(sort, () => void loadPapers())

onMounted(() => {
  document.addEventListener('keydown', closeTransientLayer)
  void refreshAll()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', closeTransientLayer)
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <div
    class="relative h-full min-h-[520px]"
    @dragenter.prevent="draggingFile = !!$event.dataTransfer?.types.includes('Files')"
    @dragover.prevent
    @drop.prevent="onFileDrop"
  >
    <div class="flex h-full flex-col">
      <header class="flex min-h-14 shrink-0 items-center gap-3 border-b border-border/50 bg-[#f7f3ec]/45 px-4 md:px-5">
        <button type="button" class="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-border/60 bg-white/45 text-muted-foreground lg:hidden" aria-label="打开文件夹" @click="folderPanelOpen = true">
          <Menu class="h-4 w-4" />
        </button>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold">{{ currentTitle }}</p>
          <p class="truncate text-[10px] text-muted-foreground">{{ currentPath && currentPath !== currentTitle ? `${currentPath} · ` : '' }}{{ papers.items.length }} 篇论文</p>
        </div>
        <label class="ml-auto hidden h-9 w-[min(360px,32vw)] items-center gap-2 rounded-xl border border-border/65 bg-white/45 px-3 sm:flex">
          <Search class="h-4 w-4 shrink-0 text-muted-foreground" />
          <input v-model="query" class="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground/65" placeholder="搜索标题或文件名" />
          <button v-if="query" type="button" class="text-muted-foreground" aria-label="清空搜索" @click="query = ''"><X class="h-3.5 w-3.5" /></button>
        </label>
        <label class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-border/60 bg-white/40 px-2.5 text-[11px] text-muted-foreground">
          <span class="hidden md:inline">排序</span>
          <select v-model="sort" class="bg-transparent text-foreground outline-none">
            <option value="updated">最近更新</option>
            <option value="created">添加时间</option>
            <option value="title">标题</option>
            <option value="opened">最近阅读</option>
          </select>
        </label>
        <button type="button" class="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-muted-foreground transition-colors hover:bg-white/55 hover:text-foreground" title="刷新文献库" aria-label="刷新文献库" @click="refreshAll">
          <RefreshCw class="h-4 w-4" :class="papers.loading && 'animate-spin'" />
        </button>
        <ImportPaperMenu :uploading="papers.uploading" :destination="currentFolder?.name || '未归档'" @upload="upload" @import-url="importUrl" />
      </header>

      <div v-if="error" class="flex min-h-11 shrink-0 items-center gap-3 border-b border-destructive/20 bg-destructive/8 px-5 text-sm text-destructive">
        <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" /><p class="min-w-0 flex-1">{{ error }}</p>
        <button type="button" class="inline-flex items-center gap-1 text-xs" @click="refreshAll"><RefreshCw class="h-3.5 w-3.5" />重试</button>
      </div>
      <p v-if="toast" class="absolute left-1/2 top-3 z-40 -translate-x-1/2 rounded-xl border border-border/60 bg-[#fffdf9] px-3 py-2 text-xs text-muted-foreground shadow-lg">{{ toast }}</p>

      <section class="grid min-h-0 flex-1 grid-cols-1 overflow-hidden bg-white/10 lg:grid-cols-[235px_minmax(0,1fr)]">
        <div class="hidden min-h-0 border-r border-border/50 bg-[#f7f3ec]/35 lg:block">
          <FolderTree
            :tree="folders.tree" :loading="folders.loading" :selected-view="selectedView" :selected-folder-id="selectedFolderId"
            @select-view="selectView" @select-folder="selectFolder" @create-root="createFolder(null)" @create-child="createFolder"
            @rename="renameFolder" @remove="removeFolder" @drop-paper="movePaper"
          />
        </div>

        <div class="flex min-h-0 min-w-0 flex-col px-4 pb-3 pt-4 md:px-5">
          <div v-if="selected.size" class="mb-3 flex min-h-9 flex-wrap items-center gap-2 rounded-xl bg-primary/6 px-2">
              <span class="inline-flex items-center gap-1 text-xs text-primary"><CheckSquare class="h-3.5 w-3.5" />已选择 {{ selected.size }} 篇</span>
              <label v-if="selectedView !== 'trash'" class="inline-flex h-8 items-center gap-1 rounded-lg border border-border/65 bg-white/40 px-2 text-xs text-muted-foreground">
                <FolderInput class="h-3.5 w-3.5" />
                <select class="bg-transparent outline-none" @change="moveSelected">
                  <option value="">移动到…</option><option value="__unfiled__">未归档</option>
                  <option v-for="folder in folders.items" :key="folder.id" :value="folder.id">{{ folder.name }}</option>
                </select>
              </label>
              <button v-if="selectedView !== 'trash'" type="button" class="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-xs text-destructive hover:bg-destructive/8" @click="trashSelected"><Trash2 class="h-3.5 w-3.5" />回收站</button>
          </div>

          <label class="mb-3 flex h-9 items-center gap-2 rounded-xl border border-border/65 bg-white/45 px-3 sm:hidden"><Search class="h-4 w-4 text-muted-foreground" /><input v-model="query" class="min-w-0 flex-1 bg-transparent text-xs outline-none" placeholder="搜索论文" /></label>

          <div class="min-h-0 flex-1 overflow-auto border-t border-border/55">
            <div class="sticky top-0 z-10 grid h-9 min-w-[820px] grid-cols-[34px_minmax(240px,1fr)_120px_90px_128px_116px] items-center gap-3 border-b border-border/55 bg-[#f4efe8]/95 px-3 text-[10px] font-medium text-muted-foreground backdrop-blur-xl">
              <label class="grid h-8 w-8 cursor-pointer place-items-center"><input type="checkbox" class="h-3.5 w-3.5 accent-primary" :checked="allSelected" aria-label="全选" @change="toggleAll" /></label>
              <span>论文</span><span>状态</span><span>页数</span><span>更新时间</span><span class="text-right">操作</span>
            </div>
            <div v-if="papers.loading && !papers.items.length" class="flex min-h-64 items-center justify-center text-muted-foreground"><Loader2 class="h-5 w-5 animate-spin" /></div>
            <div v-else-if="!papers.items.length" class="flex min-h-64 flex-col items-center justify-center px-6 text-center">
              <Inbox class="mb-3 h-9 w-9 text-muted-foreground/55" />
              <p class="text-sm font-medium">{{ query ? '没有匹配的论文' : selectedView === 'trash' ? '回收站为空' : '这里还没有论文' }}</p>
              <p class="mt-1 text-xs text-muted-foreground">{{ query ? '尝试更换关键词' : '使用右上角导入，或将 PDF 拖到页面中' }}</p>
            </div>
            <div v-else class="min-w-[820px]">
              <PaperListRow
                v-for="paper in papers.items" :key="paper.id" :paper="paper" :selected="selected.has(paper.id)"
                :folder-name="paper.folder_id ? folderMap.get(paper.folder_id)?.name : undefined" :trash="selectedView === 'trash'"
                @select="toggleSelected" @open="openPaper" @rename="renamePaper" @remove="trashPaper"
                @restore="restorePaper" @permanent="permanentPaper" @reparse="reparsePaper"
              />
            </div>
          </div>
          <p class="mt-2 text-[10px] text-muted-foreground/75">双击打开论文 · 拖动论文到左侧文件夹即可移动</p>
        </div>
      </section>
    </div>

    <div v-if="folderPanelOpen" class="fixed inset-0 z-40 bg-black/20 lg:hidden" @click="folderPanelOpen = false">
      <div class="h-full w-[280px] border-r border-border/60 bg-[#f7f3ec] shadow-2xl" @click.stop>
        <div class="flex h-12 items-center justify-between border-b border-border/50 px-4 text-sm font-medium">文件夹<button type="button" @click="folderPanelOpen = false"><X class="h-4 w-4" /></button></div>
        <FolderTree
          :tree="folders.tree" :loading="folders.loading" :selected-view="selectedView" :selected-folder-id="selectedFolderId"
          @select-view="selectView" @select-folder="selectFolder" @create-root="createFolder(null)" @create-child="createFolder"
          @rename="renameFolder" @remove="removeFolder" @drop-paper="movePaper"
        />
      </div>
    </div>

    <div v-if="draggingFile" class="pointer-events-none absolute inset-0 z-50 grid place-items-center border-2 border-dashed border-primary bg-primary/10 backdrop-blur-sm">
      <div class="rounded-2xl bg-[#fffdf9] px-8 py-5 text-center shadow-xl"><p class="text-sm font-medium">松开以导入 PDF</p><p class="mt-1 text-xs text-muted-foreground">将保存到 {{ currentFolder?.name || '未归档' }}</p></div>
    </div>
    <FolderDialog
      :open="!!folderEditor"
      :title="folderEditor?.title || ''"
      :initial-value="folderEditor?.value"
      @close="folderEditor = null"
      @submit="saveFolder"
    />
  </div>
</template>
