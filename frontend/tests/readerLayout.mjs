import assert from 'node:assert/strict'
import { createServer } from 'vite'

const vite = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { displayFormulaLane } = await vite.ssrLoadModule('/src/lib/formulaLayout.ts')
  const column = [106, 504]
  const left = [146, 420, 300, 436]
  const right = [338, 412, 464, 444]

  assert.deepEqual(displayFormulaLane(left, [left, right], column), [106, 319])
  assert.deepEqual(displayFormulaLane(right, [left, right], column), [319, 504])
  assert.equal(displayFormulaLane(left, [left], column), null)

  // 不同行的公式以及 bbox 本身重叠的异常数据不能被强行分 lane。
  assert.equal(displayFormulaLane(left, [left, [338, 460, 464, 480]], column), null)
  assert.equal(displayFormulaLane(left, [left, [290, 414, 464, 440]], column), null)
} finally {
  await vite.close()
}
