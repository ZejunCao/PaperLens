import { defineStore, acceptHMRUpdate } from 'pinia'
import { ref, watch } from 'vue'
import * as api from '@/api/papers'
import type { Paper, PaperQuery } from '@/types'

const ACTIVE = new Set(['queued', 'parsing'])

export const usePapersStore = defineStore('papers', () => {
  const items = ref<Paper[]>([])
  const loading = ref(false)
  const uploading = ref(false)
  const error = ref('')
  const activeQuery = ref<PaperQuery>({ view: 'all', sort: 'updated' })

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function hasActive() {
    return items.value.some((p) => ACTIVE.has(p.status))
  }

  function stopStatusPoll() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startStatusPoll() {
    if (pollTimer) return
    pollTimer = setInterval(async () => {
      try {
        const data = await api.fetchPapers(activeQuery.value)
        items.value = data.items
        if (!hasActive()) stopStatusPoll()
      } catch {
        /* 轮询失败下次再试 */
      }
    }, 1500)
  }

  watch(
    items,
    () => {
      if (hasActive()) startStatusPoll()
      else stopStatusPoll()
    },
    { deep: true },
  )

  async function load(query: PaperQuery = activeQuery.value) {
    loading.value = true
    error.value = ''
    activeQuery.value = { ...query }
    try {
      const data = await api.fetchPapers(activeQuery.value)
      items.value = data.items
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function upload(file: File, folderId?: string | null) {
    uploading.value = true
    error.value = ''
    try {
      const paper = await api.uploadPaper(file, folderId)
      items.value = [paper, ...items.value.filter((p) => p.id !== paper.id)]
      return paper
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      uploading.value = false
    }
  }

  async function importFromUrl(url: string, folderId?: string | null) {
    uploading.value = true
    error.value = ''
    try {
      const paper = await api.importPaperFromUrl(url, folderId)
      items.value = [paper, ...items.value.filter((p) => p.id !== paper.id)]
      return paper
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      uploading.value = false
    }
  }

  async function rename(id: string, title: string) {
    const paper = await api.renamePaper(id, title)
    const idx = items.value.findIndex((p) => p.id === id)
    if (idx >= 0) items.value[idx] = paper
    return paper
  }

  async function remove(id: string) {
    await api.deletePaper(id)
    items.value = items.value.filter((p) => p.id !== id)
  }

  async function move(id: string, folderId: string | null) {
    await api.movePaper(id, folderId)
    await load()
  }

  async function restore(id: string) {
    await api.restorePaper(id)
    items.value = items.value.filter((p) => p.id !== id)
  }

  async function removePermanently(id: string) {
    await api.permanentlyDeletePaper(id)
    items.value = items.value.filter((p) => p.id !== id)
  }

  async function getOne(id: string) {
    const cached = items.value.find((p) => p.id === id)
    if (cached) return cached
    const paper = await api.fetchPaper(id)
    items.value = [paper, ...items.value.filter((p) => p.id !== paper.id)]
    return paper
  }

  async function reparse(id: string) {
    error.value = ''
    await api.retryParse(id)
    const paper = await api.fetchPaper(id)
    const idx = items.value.findIndex((p) => p.id === id)
    if (idx >= 0) items.value[idx] = paper
    else items.value = [paper, ...items.value]
    return paper
  }

  async function refreshMetadata(id: string) {
    const paper = await api.refreshPaperMetadata(id)
    const idx = items.value.findIndex((item) => item.id === id)
    if (idx >= 0) items.value[idx] = paper
    return paper
  }

  return {
    items,
    loading,
    uploading,
    error,
    activeQuery,
    load,
    upload,
    importFromUrl,
    rename,
    remove,
    move,
    restore,
    removePermanently,
    reparse,
    refreshMetadata,
    getOne,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(usePapersStore, import.meta.hot))
}
