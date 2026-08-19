import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 产品仅保留米白亮色主题 */
export const useUiStore = defineStore(
  'ui',
  () => {
    /** 阅读器偏好在论文之间共享，并由持久化插件保存到 localStorage。 */
    const readerPdfScale = ref(1)
    const readerTextScale = ref(1)
    const readerSplitPercent = ref(50)

    function initTheme() {
      document.documentElement.classList.remove('dark')
    }

    return {
      initTheme,
      readerPdfScale,
      readerTextScale,
      readerSplitPercent,
    }
  },
  {
    persist: {
      key: 'paperlens-ui-preferences',
      pick: ['readerPdfScale', 'readerTextScale', 'readerSplitPercent'],
    },
  },
)
