export interface PageTextLine {
  text: string
  x: number
  y: number
  /** 0 = 页顶，1 = 页底 */
  topRatio: number
}

export interface PageTextBlock {
  page: number
  lines: PageTextLine[]
}
