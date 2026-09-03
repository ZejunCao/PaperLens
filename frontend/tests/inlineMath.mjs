import assert from 'node:assert/strict'
import katex from 'katex'
import { createServer } from 'vite'

const vite = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { normalizeSpacedLatex, splitInlineMath } = await vite.ssrLoadModule(
    '/src/lib/inlineMath.ts',
  )

  const assertKatex = (latex) => {
    assert.doesNotThrow(() =>
      katex.renderToString(latex, {
        throwOnError: true,
        strict: 'ignore',
        macros: { '\\pmb': '\\boldsymbol' },
      }),
    )
  }

  // 同名 array 嵌套必须作为一整个公式切分，不能在内层 end 提前终止。
  const nestedArray = String.raw`前文 \begin{array} { r } { \left[ \begin{array} { l } { a } \\ { b } \end{array} \right] } \end{array} 后文`
  const nestedChunks = splitInlineMath(nestedArray)
  const nestedMath = nestedChunks.filter((chunk) => chunk.kind === 'math')
  assert.equal(nestedMath.length, 1)
  assertKatex(nestedMath[0].text)

  // 无花括号的单字符样式参数不能粘成未知命令 `\pmbq`。
  const pmb = normalizeSpacedLatex(String.raw`\phi ( \pmb q ^ { ( i ) } )`)
  assert.match(pmb, /\\pmb\{q\}/)
  assertKatex(pmb)

  // 嵌套组内的声明式控制词必须保留参数边界，不能变成 `\bfQ`。
  const dottedBold = normalizeSpacedLatex(String.raw`\dot { { \bf Q } } _ { [ t ] }`)
  assert.match(dottedBold, /\\mathbf(?:\s*)\{Q\}/)
  assert.doesNotMatch(dottedBold, /\\bfQ/)
  assertKatex(dottedBold)

  // 关系控制词后的变量边界同样不能被吞掉。
  for (const raw of [String.raw`1 \leq j \leq i`, String.raw`n \neq l`]) {
    const normalized = normalizeSpacedLatex(raw)
    assertKatex(normalized)
    assert.doesNotMatch(normalized, /\\(?:leq|neq)[A-Za-z]/)
  }

  // 控制词只允许完整匹配；`\intercal` 不能被 `\in` 规则拆开。
  const intercal = normalizeSpacedLatex(String.raw`k _ { j } ^ { \intercal }`)
  assert.match(intercal, /\\intercal/)
  assertKatex(intercal)

  // MinerU 多写的“反斜杠 + 空格 + 单字母”应还原为变量，而非未知命令。
  for (const raw of [String.raw`\ j \leq i`, String.raw`\ v _ { t }`]) {
    const normalized = normalizeSpacedLatex(raw)
    assertKatex(normalized)
    assert.doesNotMatch(normalized, /\\[jv](?![A-Za-z])/)
  }

  // 多层外部分组要从最外层开始扫描，不能留下额外的右花括号。
  const grouped = splitInlineMath(String.raw`对 { { \bf { M } } _ { t } } 不作假设`)
  const groupedMath = grouped.filter((chunk) => chunk.kind === 'math')
  assert.equal(groupedMath.length, 1)
  assertKatex(groupedMath[0].text)

  // 旧式 `\em` 字体声明统一转为 KaTeX 支持的参数式命令。
  assertKatex(normalizeSpacedLatex(String.raw`\mathbf { \em u } _ { t }`))

  // 代码/元数据里的普通下划线标识符不应被当成公式。
  for (const raw of ['x_rolled', 'openai_compatible', 'neco_a_01174', 'tacl_a_00353']) {
    assert.deepEqual(splitInlineMath(raw), [{ kind: 'text', text: raw }])
  }

  // 锚定卡片复用 splitInlineMath：显式 array 必须成为 KaTeX 块，不能泄漏到文本节点。
  const pinnedParagraph = String.raw`我们观察到 \mathbf { S } _ { t } 可写为 \begin{array} { r } { \mathbf { S } _ { t } = \sum _ { i = 1 } ^ { t } \mathbf { u } _ { i } \mathbf { k } _ { i } ^ { \top } } \end{array}。回顾 \begin{array} { r } { \mathbf { S } _ { t } = \sum _ { i = 1 } ^ { t } v _ { i } \pmb { k } _ { i } ^ { \top } } \end{array}。`
  const pinnedChunks = splitInlineMath(pinnedParagraph)
  assert.equal(pinnedChunks.filter((chunk) => chunk.kind === 'math' && chunk.text.includes('begin')).length, 2)
  assert.equal(pinnedChunks.some((chunk) => chunk.kind === 'text' && /\\(?:begin|mathbf)/.test(chunk.text)), false)
  for (const chunk of pinnedChunks.filter((item) => item.kind === 'math')) assertKatex(chunk.text)
} finally {
  await vite.close()
}
