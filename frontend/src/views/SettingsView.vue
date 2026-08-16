<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { AlertCircle, Check, Loader2, Save } from 'lucide-vue-next'
import { fetchLlmSettings, saveLlmSettings } from '@/api/settings'

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const toast = ref('')

const baseUrl = ref('https://api.openai.com/v1')
const apiKey = ref('')
const model = ref('')
const keySet = ref(false)
const keyMasked = ref('')
const configured = ref(false)

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const s = await fetchLlmSettings()
    baseUrl.value = s.base_url || 'https://api.openai.com/v1'
    model.value = s.model || ''
    keySet.value = s.api_key_set
    keyMasked.value = s.api_key_masked
    configured.value = s.configured
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})

async function onSave() {
  saving.value = true
  error.value = ''
  toast.value = ''
  try {
    const s = await saveLlmSettings({
      base_url: baseUrl.value.trim(),
      api_key: apiKey.value.trim(),
      model: model.value.trim(),
    })
    apiKey.value = ''
    keySet.value = s.api_key_set
    keyMasked.value = s.api_key_masked
    configured.value = s.configured
    model.value = s.model
    baseUrl.value = s.base_url
    toast.value = s.configured ? '已保存，打开论文后停留在某一页 1 秒将开始翻译。' : '已保存。请填写 Model；本地接口可不填 Key。'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-6 p-4 md:p-6">
    <div>
      <h1 class="text-lg font-semibold tracking-tight">模型设置</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        使用 OpenAI 兼容接口（官方 API、DeepSeek、Ollama、vLLM 等）。密钥只存在本机
        <code class="rounded bg-white px-1 text-xs ring-1 ring-border/60">data/llm_config.json</code>，不会上传仓库。
      </p>
    </div>

    <div
      v-if="error"
      class="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive"
    >
      <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" />
      <p>{{ error }}</p>
    </div>

    <p
      v-if="toast"
      class="flex items-center gap-2 rounded-2xl border border-border/70 bg-white px-4 py-2 text-sm text-foreground"
    >
      <Check class="h-4 w-4 text-primary" />
      {{ toast }}
    </p>

    <div v-if="loading" class="flex justify-center py-12 text-muted-foreground">
      <Loader2 class="h-6 w-6 animate-spin" />
    </div>

    <form v-else class="space-y-4 rounded-2xl border border-border/70 bg-white p-5 shadow-sm" @submit.prevent="onSave">
      <label class="block space-y-1.5">
        <span class="text-xs font-medium text-muted-foreground">Base URL</span>
        <input
          v-model="baseUrl"
          class="h-10 w-full rounded-xl border border-border/80 bg-[#faf7f2] px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15"
          placeholder="https://api.openai.com/v1 或 http://127.0.0.1:11434/v1"
          autocomplete="off"
        />
      </label>

      <label class="block space-y-1.5">
        <span class="text-xs font-medium text-muted-foreground">API Key</span>
        <input
          v-model="apiKey"
          type="password"
          class="h-10 w-full rounded-xl border border-border/80 bg-[#faf7f2] px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15"
          :placeholder="keySet ? `已保存 ${keyMasked}，留空则保持不变` : 'sk-…（本地 Ollama 可留空）'"
          autocomplete="off"
        />
      </label>

      <label class="block space-y-1.5">
        <span class="text-xs font-medium text-muted-foreground">Model</span>
        <input
          v-model="model"
          class="h-10 w-full rounded-xl border border-border/80 bg-[#faf7f2] px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/15"
          placeholder="gpt-4o-mini / deepseek-chat / llama3.1"
          autocomplete="off"
        />
      </label>

      <p class="text-xs text-muted-foreground">
        当前状态：{{ configured ? '已配置，阅读时按页翻译' : '未就绪' }}
      </p>

      <button
        type="submit"
        class="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
        :disabled="saving"
      >
        <Loader2 v-if="saving" class="h-4 w-4 animate-spin" />
        <Save v-else class="h-4 w-4" />
        保存
      </button>
    </form>
  </div>
</template>
