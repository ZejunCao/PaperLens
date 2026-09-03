import assert from 'node:assert/strict'
import { createServer } from 'vite'

const vite = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { displayFormulaLane, formulaHasAdjacentText } = await vite.ssrLoadModule(
    '/src/lib/formulaLayout.ts',
  )
  const { bboxContainsCenter, detectPageColumns, toBBox } = await vite.ssrLoadModule(
    '/src/lib/layoutGeometry.ts',
  )
  const column = [106, 504]
  const left = [146, 420, 300, 436]
  const right = [338, 412, 464, 444]

  assert.deepEqual(displayFormulaLane(left, [left, right], column), [106, 319])
  assert.deepEqual(displayFormulaLane(right, [left, right], column), [319, 504])
  assert.equal(displayFormulaLane(left, [left], column), null)

  // 不同行的公式以及 bbox 本身重叠的异常数据不能被强行分 lane。
  assert.equal(displayFormulaLane(left, [left, [338, 460, 464, 480]], column), null)
  assert.equal(displayFormulaLane(left, [left, [290, 414, 464, 440]], column), null)

  // 公式右侧有同一视觉行的说明文字时，应保留公式原 bbox，而不是整栏居中。
  assert.equal(formulaHasAdjacentText([150, 471, 208, 491], [[254, 477, 459, 486]], column), true)
  assert.equal(formulaHasAdjacentText([150, 471, 208, 491], [[254, 530, 459, 540]], column), false)
  assert.equal(formulaHasAdjacentText([150, 471, 208, 491], [[360, 477, 500, 486]], column), false)

  assert.deepEqual(toBBox([10, 20, 30, 40]), [10, 20, 30, 40])
  assert.equal(toBBox([10, 20, 30]), null)
  assert.equal(toBBox([10, 20, Number.NaN, 40]), null)
  assert.equal(bboxContainsCenter([0, 0, 100, 100], [90, 40, 120, 60]), true)
  assert.equal(bboxContainsCenter([0, 0, 100, 100], [140, 40, 160, 60]), false)

  const twoColumns = detectPageColumns(
    [
      { type: 'paragraph', bbox: [45, 80, 265, 180] },
      { type: 'paragraph', bbox: [330, 80, 550, 180] },
      { type: 'figure', bbox: [40, 200, 560, 380] },
    ],
    600,
  )
  assert.equal(twoColumns.two, true)
  assert.deepEqual(twoColumns.left, [45, 265])
  assert.deepEqual(twoColumns.right, [330, 550])

  const singleColumn = detectPageColumns(
    [{ type: 'paragraph', bbox: [60, 80, 540, 180] }],
    600,
  )
  assert.equal(singleColumn.two, false)
  assert.deepEqual(singleColumn.left, [60, 540])
} finally {
  await vite.close()
}
