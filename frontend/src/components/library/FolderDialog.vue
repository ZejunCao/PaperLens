<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  initialValue?: string
}>()

const emit = defineEmits<{
  close: []
  submit: [name: string]
}>()

const input = ref<HTMLInputElement | null>(null)
const value = ref('')

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    value.value = props.initialValue || ''
    await nextTick()
    input.value?.focus()
    input.value?.select()
  },
)

function submit() {
  const name = value.value.trim()
  if (name) emit('submit', name)
}

function closeWithKeyboard(event: KeyboardEvent) {
  if (props.open && event.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', closeWithKeyboard))
onBeforeUnmount(() => document.removeEventListener('keydown', closeWithKeyboard))
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-[70] grid place-items-center bg-black/20 p-4" @click.self="emit('close')">
    <form class="w-full max-w-sm rounded-2xl border border-border/70 bg-[#fffdf9] p-5 shadow-2xl" @submit.prevent="submit">
      <h3 class="text-sm font-semibold">{{ title }}</h3>
      <p class="mt-1 text-xs text-muted-foreground">用于整理本地论文，不会创建磁盘目录。</p>
      <input
        ref="input"
        v-model="value"
        maxlength="160"
        class="mt-4 h-10 w-full rounded-xl border border-border bg-white px-3 text-sm outline-none ring-primary focus:ring-2"
        placeholder="输入文件夹名称"
      />
      <div class="mt-4 flex justify-end gap-2">
        <button type="button" class="h-9 rounded-xl px-3 text-xs text-muted-foreground hover:bg-accent" @click="emit('close')">取消</button>
        <button type="submit" class="h-9 rounded-xl bg-primary px-4 text-xs font-medium text-primary-foreground disabled:opacity-40" :disabled="!value.trim()">保存</button>
      </div>
    </form>
  </div>
</template>
