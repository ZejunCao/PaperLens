export type FormulaBBox = readonly [number, number, number, number]

function sameBox(a: FormulaBBox, b: FormulaBBox): boolean {
  return a.every((value, index) => Math.abs(value - b[index]!) < 0.01)
}

function verticalOverlapRatio(a: FormulaBBox, b: FormulaBBox): number {
  const overlap = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]))
  return overlap / Math.max(1, Math.min(a[3] - a[1], b[3] - b[1]))
}

/**
 * 同一视觉行存在多个互不重叠的行间公式时，为目标公式划分独立横向区域。
 * 单公式或 bbox 相互覆盖时返回 null，由调用方沿用整栏居中策略。
 */
export function displayFormulaLane(
  target: FormulaBBox,
  candidates: FormulaBBox[],
  column: readonly [number, number],
): readonly [number, number] | null {
  const row = candidates
    .filter((box) => {
      const centerX = (box[0] + box[2]) / 2
      return (
        centerX >= column[0] &&
        centerX <= column[1] &&
        verticalOverlapRatio(target, box) >= 0.3
      )
    })
    .sort((a, b) => a[0] - b[0])

  if (row.length < 2) return null
  for (let index = 1; index < row.length; index++) {
    if (row[index]![0] < row[index - 1]![2] + 2) return null
  }
  const targetIndex = row.findIndex((box) => sameBox(box, target))
  if (targetIndex < 0) return null

  const previous = row[targetIndex - 1]
  const next = row[targetIndex + 1]
  const left = previous ? (previous[2] + target[0]) / 2 : column[0]
  const right = next ? (target[2] + next[0]) / 2 : column[1]
  return right - left >= 12 ? [left, right] : null
}
