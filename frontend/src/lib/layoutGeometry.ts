import type { BBox, BlockType } from '@/types/document'

export type PageColumns = {
  two: boolean
  left: readonly [number, number]
  right: readonly [number, number]
}

export function toBBox(value: readonly number[] | null | undefined): BBox | null {
  if (!value || value.length < 4) return null
  const [x0, y0, x1, y1] = value
  if (![x0, y0, x1, y1].every((item) => Number.isFinite(item))) return null
  return [x0!, y0!, x1!, y1!]
}

export function detectPageColumns(
  blocks: ReadonlyArray<{ bbox: BBox; type: BlockType }>,
  pageWidth: number,
): PageColumns {
  const mid = pageWidth / 2
  let leftStart = Infinity
  let leftEnd = 0
  let rightStart = Infinity
  let rightEnd = 0

  for (const block of blocks) {
    const [x0, , x1] = block.bbox
    const width = x1 - x0
    if (block.type === 'formula' || width < 70 || width > pageWidth * 0.62) continue
    if ((x0 + x1) / 2 < mid) {
      leftStart = Math.min(leftStart, x0)
      leftEnd = Math.max(leftEnd, x1)
    } else {
      rightStart = Math.min(rightStart, x0)
      rightEnd = Math.max(rightEnd, x1)
    }
  }

  const gap = rightStart - leftEnd
  if (
    Number.isFinite(leftStart) &&
    Number.isFinite(rightStart) &&
    leftEnd - leftStart > 90 &&
    rightEnd - rightStart > 90 &&
    gap > 10 &&
    leftEnd < pageWidth * 0.55 &&
    rightStart > pageWidth * 0.45
  ) {
    return { two: true, left: [leftStart, leftEnd], right: [rightStart, rightEnd] }
  }

  let start = Infinity
  let end = 0
  for (const block of blocks) {
    const [x0, , x1] = block.bbox
    const width = x1 - x0
    if (block.type === 'formula' || block.type === 'figure') continue
    if (width < pageWidth * 0.4 || width > pageWidth * 0.96) continue
    start = Math.min(start, x0)
    end = Math.max(end, x1)
  }
  if (!Number.isFinite(start) || end - start < pageWidth * 0.35) {
    start = pageWidth * 0.1
    end = pageWidth * 0.9
  }
  return { two: false, left: [start, end], right: [start, end] }
}

export function bboxCenter(box: BBox): readonly [number, number] {
  return [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
}

export function bboxContainsCenter(outer: BBox, inner: BBox, toleranceX = 24, toleranceY = 10): boolean {
  const [x, y] = bboxCenter(inner)
  return (
    x >= outer[0] - toleranceX &&
    x <= outer[2] + toleranceX &&
    y >= outer[1] - toleranceY &&
    y <= outer[3] + toleranceY
  )
}
