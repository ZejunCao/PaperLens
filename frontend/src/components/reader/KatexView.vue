<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { normalizeSpacedLatex } from '@/lib/inlineMath'

const props = withDefaults(
  defineProps<{
    latex: string
    display?: boolean
    title?: string
    fitWidth?: number
    fitHeight?: number
  }>(),
  { display: false },
)

const emit = defineEmits<{ painted: [] }>()

const el = ref<HTMLElement | null>(null)
const error = ref('')
const layout = computed(() => !!props.fitWidth && props.fitWidth >= 2)

const rendered = computed(() => normalizeSpacedLatex((props.latex || '').trim()))

function paint() {
  if (!el.value) return
  error.value = ''
  el.value.style.transform = 'none'
  try {
    katex.render(rendered.value, el.value, {
      throwOnError: false,
      displayMode: props.display,
      strict: 'ignore',
      output: 'html',
      macros: {
        '\\pmb': '\\boldsymbol',
      },
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    el.value.textContent = props.latex
  }
  nextTick(() =>
    requestAnimationFrame(() => {
      fitToBox()
      emit('painted')
    }),
  )
}

function fitToBox() {
  const host = el.value
  if (!host || !layout.value) return
  host.style.transform = 'none'
  const nw = Math.max(host.scrollWidth, 1)
  const nh = Math.max(host.scrollHeight, 1)
  if (props.display) {
    host.style.transformOrigin = 'center top'
    const inner = host.querySelector('.katex') as HTMLElement | null
    const iw = Math.max(inner?.scrollWidth || nw, 1)
    const sx = props.fitWidth! / iw
    const sy = props.fitHeight && props.fitHeight > 2 ? props.fitHeight / nh : 1
    const s = Math.min(1, sx, sy)
    if (s < 0.97) host.style.transform = `scale(${Math.max(s, 0.45)})`
    return
  }
  // 行内公式按正文字号基线对齐，不要按框高缩放（会把主符号拽下去）
}

onMounted(paint)
watch(
  () => [props.latex, props.display, props.fitWidth, props.fitHeight] as const,
  () => paint(),
)
</script>

<template>
  <span
    ref="el"
    class="katex-host inline-block select-text leading-none"
    :class="layout ? (display ? 'layout-display' : 'layout-inline max-w-none') : 'max-w-full'"
    :title="title || latex"
  />
</template>

<style>
.katex-host,
.katex-host .katex,
.katex-host .katex * {
  user-select: text;
  -webkit-user-select: text;
}
.katex-host.layout-display {
  display: block;
  width: 100%;
}
.katex-host.layout-display .katex-display {
  margin: 0;
  width: 100%;
  text-align: center;
}
.katex-host.layout-display .katex-display > .katex {
  white-space: nowrap;
}
.katex-host.layout-inline {
  vertical-align: baseline;
}
.katex-host.layout-inline .katex {
  font-size: 1em !important;
  line-height: 1;
  vertical-align: baseline;
}
</style>
