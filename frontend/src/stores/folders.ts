import { acceptHMRUpdate, defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as api from '@/api/papers'
import type { Folder } from '@/types'

export interface FolderNode extends Folder {
  children: FolderNode[]
}

export const useFoldersStore = defineStore('folders', () => {
  const items = ref<Folder[]>([])
  const loading = ref(false)
  const error = ref('')

  const tree = computed<FolderNode[]>(() => {
    const nodes = new Map<string, FolderNode>()
    for (const folder of items.value) nodes.set(folder.id, { ...folder, children: [] })
    const roots: FolderNode[] = []
    for (const node of nodes.values()) {
      const parent = node.parent_id ? nodes.get(node.parent_id) : undefined
      if (parent) parent.children.push(node)
      else roots.push(node)
    }
    const sort = (list: FolderNode[]) => {
      list.sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, 'zh-CN'))
      list.forEach((node) => sort(node.children))
    }
    sort(roots)
    return roots
  })

  async function load() {
    loading.value = true
    error.value = ''
    try {
      items.value = (await api.fetchFolders()).items
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function create(name: string, parentId: string | null = null) {
    const folder = await api.createFolder(name, parentId)
    items.value = [...items.value, folder]
    return folder
  }

  async function rename(id: string, name: string) {
    const folder = await api.updateFolder(id, { name })
    const index = items.value.findIndex((item) => item.id === id)
    if (index >= 0) items.value[index] = folder
  }

  async function remove(id: string) {
    await api.deleteFolder(id)
    await load()
  }

  return { items, tree, loading, error, load, create, rename, remove }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useFoldersStore, import.meta.hot))
}
