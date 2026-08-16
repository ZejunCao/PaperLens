import { defineStore } from 'pinia'

/** 产品仅保留米白亮色主题 */
export const useUiStore = defineStore('ui', () => {
  function initTheme() {
    document.documentElement.classList.remove('dark')
  }

  return { initTheme }
})
