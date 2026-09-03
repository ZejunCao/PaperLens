export type RichChunk = { kind: 'text' | 'math'; text: string; display?: boolean }

function pushText(out: RichChunk[], text: string) {
  if (!text) return
  const last = out[out.length - 1]
  if (last?.kind === 'text') last.text += text
  else out.push({ kind: 'text', text })
}

function isAsciiLetter(ch: string): boolean {
  return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z')
}

function isCjk(ch: string): boolean {
  return /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/.test(ch)
}

/** 中文标点：公式与正文的分界 */
function isCnBoundary(ch: string): boolean {
  return isCjk(ch) || /[，。、；：？！""''【】《》]/.test(ch)
}

function matchBalancedBrace(s: string, open: number): number {
  if (s[open] !== '{') return -1
  let depth = 0
  for (let i = open; i < s.length; i++) {
    const ch = s[i]!
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return i
    }
  }
  return -1
}

/** 压缩普通数学原子间空格，但保留 `\\leq j` 这类控制词的参数边界。 */
function compactAdjacentMathAtoms(s: string): string {
  return s.replace(
    /([A-Za-z0-9}\])])\s+(?!\\[A-Za-z*])([A-Za-z0-9{(^_])/g,
    (_match, left: string, right: string, offset: number, source: string) => {
      if (isAsciiLetter(left)) {
        let commandStart = offset
        while (commandStart > 0 && isAsciiLetter(source[commandStart - 1]!)) commandStart--
        if (commandStart > 0 && source[commandStart - 1] === '\\') return `${left} ${right}`
      }
      return `${left}${right}`
    },
  )
}

/** MinerU/译文：把带空格的 LaTeX 压成 KaTeX 可渲染形式 */
export function normalizeSpacedLatex(raw: string): string {
  let s = raw.replace(/\s+/g, ' ').trim()
  if (!s) return s

  // 少数链路会把 \times 误变成 TAB+imes（JS/Python 字符串里 \t 转义）
  s = s.replace(/\u0009imes/g, '\\times')
  // N × F：必须保留边界，否则 KaTeX 会把 N\times 里的 \t 当成 tab 转义
  s = s.replace(/([0-9A-Za-z])\s*\\times\s*([0-9A-Za-z])/g, '$1{\\times}$2')

  // `\ bar` -> `\bar`；但 `\ j` / `\ v` 是 MinerU 多写的转义空格，
  // 单字母不能拼成不存在或语义不同的控制词（如 `\j`、重音命令 `\v`）。
  s = s.replace(/\\ +([A-Za-z]+)/g, (_match, word: string) =>
    word.length === 1 ? word : `\\${word}`,
  )
  s = s.replace(/\\{2,}(?=[A-Za-z*])/g, '\\')
  // 将旧式字体声明统一成有明确参数的 KaTeX 命令，避免 `\bf Q` 被误拼成
  // `\bfQ`，也兼容 KaTeX 不支持的 `\em`。
  const legacyFontCommands: Record<string, string> = {
    bf: 'mathbf',
    rm: 'mathrm',
    it: 'mathit',
    em: 'mathit',
  }
  s = s.replace(
    /\\(bf|rm|it|em)(?=\s*(?:\{|[A-Za-z0-9]))/g,
    (_match, command: string) => `\\${legacyFontCommands[command]}`,
  )
  // MinerU 偶尔省略单字符参数的花括号，如 `\pmb q`。若直接压缩空格会
  // 变成不存在的 `\pmbq` 命令，KaTeX 会将其显示为红色错误文本。
  s = s.replace(
    /\\(pmb|boldsymbol|mathbf|mathrm|mathit|mathsf|mathtt|mathcal|mathbb|mathfrak|bar|hat|tilde|vec)\s+([A-Za-z0-9])/g,
    '\\$1{$2}',
  )

  for (let pass = 0; pass < 16; pass++) {
    const prev = s
    let out = ''
    let i = 0
    while (i < s.length) {
      // \cmd[*]{...}（支持嵌套花括号）
      if (s[i] === '\\' && isAsciiLetter(s[i + 1] || '')) {
        let j = i + 1
        while (j < s.length && isAsciiLetter(s[j]!)) j++
        const star = s[j] === '*' ? '*' : ''
        if (star) j++
        while (s[j] === ' ') j++
        if (s[j] === '{') {
          const close = matchBalancedBrace(s, j)
          if (close > j) {
            // 组内仍可能有必须保留的控制词边界（如 `\\dot{{\\bf Q}}` 中的
            // `\\bf Q`）；不能在递归规范化后再无条件删除全部空格。
            const body = normalizeSpacedLatex(s.slice(j + 1, close))
            out += `${s.slice(i, j)}${star}{${body}}`
            i = close + 1
            continue
          }
        }
      }
      // _{...} / ^{...}
      if ((s[i] === '_' || s[i] === '^') && s[i + 1]) {
        let j = i + 1
        while (s[j] === ' ') j++
        if (s[j] === '{') {
          const close = matchBalancedBrace(s, j)
          if (close > j) {
            const body = normalizeSpacedLatex(s.slice(j + 1, close))
            out += `${s[i]}{${body}}`
            i = close + 1
            continue
          }
        }
      }
      out += s[i]
      i++
    }
    s = out
      .replace(/\\left\s*\(/g, '\\left(')
      .replace(/\\right\s*\)/g, '\\right)')
      .replace(/\\left\s*\[/g, '\\left[')
      .replace(/\\right\s*\]/g, '\\right]')
      .replace(/\(\s+/g, '(')
      .replace(/\s+\)/g, ')')
      .replace(/\s*,\s*/g, ',')
      .replace(/\s*\.\s*(?=[}\s]|$)/g, '.')
      .replace(/\s*=\s*/g, '=')
      // 控制词必须按完整单词匹配；否则会把 `\intercal` 拆成 `\in tercal`。
      .replace(/\s*\\in(?![A-Za-z])\s*/g, '\\in ')
      .replace(/\s*\\doteq(?![A-Za-z])\s*/g, '\\doteq ')
      .replace(/\s*\\times(?![A-Za-z])\s*/g, '\\times ')
      .replace(/\s*\\cdot(?![A-Za-z])\s*/g, '\\cdot ')
      .replace(/\{\s+/g, '{')
      .replace(/\s+\}/g, '}')
      // 勿把 `N \times` 拆成 `N\` + `times`；也勿把 `\times F` 压成 `\timesF`（\t 转义）
    s = compactAdjacentMathAtoms(s)
    if (s === prev) break
  }
  s = s.replace(/\\{2,}(?=[A-Za-z*])/g, '\\')
  // 兜底：字母紧贴 \times 时加花括号，避免 `\t` 被 TeX 当成 tab
  s = s.replace(/([A-Za-z0-9])\\times/g, '$1{\\times}')
  s = s.replace(/\\times([A-Za-z0-9])/g, '{\\times}$1')
  return s
}

function looksLikeMath(raw: string): boolean {
  return /\\|[\^_]|[{}]|[A-Za-z]\s*_\s*\{|[A-Za-z]\s*\^\s*\{/.test(raw)
}

/** 从 i 起扫描一整段 MinerU/LaTeX（含 `A _ { l }`、`\mathbb { R } ^ { N \times F }`） */
function scanLatexSpan(s: string, start: number): number {
  let j = start
  let brace = 0

  if (s[start] === '\\') {
    while (j < s.length) {
      const ch = s[j]!
      if (brace === 0 && isCnBoundary(ch)) break
      if (ch === '{') {
        brace++
        j++
        continue
      }
      if (ch === '}') {
        if (brace > 0) brace--
        j++
        continue
      }
      if (ch === '\\') {
        j++
        if (j < s.length && isAsciiLetter(s[j]!)) {
          while (j < s.length && isAsciiLetter(s[j]!)) j++
          if (s[j] === '*') j++
        } else if (j < s.length) j++
        continue
      }
      if (ch === '^' || ch === '_') {
        j++
        while (s[j] === ' ') j++
        if (s[j] === '{') {
          const close = matchBalancedBrace(s, j)
          if (close > j) j = close + 1
        }
        continue
      }
      j++
    }
  } else {
    // `A _ { l } ( x ) = V ^ { \prime }` 等无 leading `\` 的片段
    while (j < s.length) {
      const ch = s[j]!
      if (brace === 0 && isCnBoundary(ch)) break
      if (ch === '{') {
        brace++
        j++
        continue
      }
      if (ch === '}') {
        if (brace > 0) brace--
        j++
        continue
      }
      if (ch === '\\') {
        j++
        if (j < s.length && isAsciiLetter(s[j]!)) {
          while (j < s.length && isAsciiLetter(s[j]!)) j++
          if (s[j] === '*') j++
        } else if (j < s.length) j++
        continue
      }
      if (ch === '^' || ch === '_') {
        j++
        while (s[j] === ' ') j++
        if (s[j] === '{') {
          const close = matchBalancedBrace(s, j)
          if (close > j) j = close + 1
        }
        continue
      }
      // 英文单词（is / growth）且不在括号/花括号内 → 结束
      if (brace === 0 && isAsciiLetter(ch)) {
        let k = j
        while (k < s.length && isAsciiLetter(s[k]!)) k++
        const word = s.slice(j, k)
        if (word.length > 1 && !/^[A-Z]$/.test(word)) break
      }
      j++
    }
  }

  while (j > start && s[j - 1] === ' ') j--
  return j
}

function mathSpanStart(s: string, i: number): boolean {
  const ch = s[i]!
  if (ch === '\\') return true
  // MinerU 常把命令整体包在花括号里：`{ \\pmb{k} }`。从内部反斜杠
  // 开始会留下一个无配对的 `}`，所以应把外层分组一并交给 KaTeX。
  if (ch === '{') {
    let k = i + 1
    while (s[k] === ' ' || s[k] === '\t' || s[k] === '{') k++
    return s[k] === '\\'
  }
  if (isAsciiLetter(ch) || /[0-9]/.test(ch)) {
    // 不从标识符中间重新起扫；否则 `neco_a_01174` 虽在开头被排除，仍会
    // 从中间的 `a_01174` 被二次误判为公式。
    if (i > 0 && /[A-Za-z0-9_]/.test(s[i - 1]!)) return false
    let k = i + 1
    while (k < s.length && k < i + 12) {
      const c = s[k]!
      if (isCnBoundary(c)) return false
      if (c === '_') {
        const identifier = s.slice(i).match(/^[A-Za-z0-9_]+/)?.[0] || ''
        if ((identifier.match(/_/g) || []).length > 1) return false
        let suffix = k + 1
        while (s[suffix] === ' ' || s[suffix] === '\t') suffix++
        if (s[suffix] === '{') return true
        let suffixEnd = suffix
        while (suffixEnd < s.length && isAsciiLetter(s[suffixEnd]!)) suffixEnd++
        // `x_i` 是公式，`x_rolled` / `openai_compatible` 是普通标识符。
        return suffixEnd - suffix <= 1
      }
      if (c === '^' || c === '{' || c === '\\') return true
      if (c !== ' ' && c !== '\t' && c !== '(') return false
      k++
    }
    return false
  }
  if (ch === '(') {
    let k = i + 1
    while (k < s.length && (s[k] === ' ' || s[k] === '\t')) k++
    const n = s[k]
    return !!n && (n === '\\' || isAsciiLetter(n) || /[0-9]/.test(n))
  }
  return false
}

/** 在中文/英文混合句子里找出 MinerU 风格公式段 */
function splitMixedTextMath(s: string, out: RichChunk[]) {
  let i = 0
  while (i < s.length) {
    if (mathSpanStart(s, i)) {
      const end = scanLatexSpan(s, i)
      const raw = s.slice(i, end)
      if (looksLikeMath(raw)) {
        out.push({ kind: 'math', text: normalizeSpacedLatex(raw), display: false })
        i = end
        continue
      }
    }
    const nextStart = (() => {
      for (let k = i + 1; k < s.length; k++) {
        if (mathSpanStart(s, k)) return k
      }
      return s.length
    })()
    pushText(out, s.slice(i, nextStart))
    i = nextStart
  }
}

type DelimitedMath = { start: number; end: number; latex: string; display: boolean }

/**
 * 找到下一个显式公式定界符。
 *
 * 这里不能用 `\\begin...\\end` 的非贪婪正则：同名环境可以嵌套，例如 MinerU
 * 常用外层 array 包住一个列向量 array，正则会在内层的 `\\end{array}` 提前结束。
 */
function findDelimitedMath(s: string, from: number): DelimitedMath | null {
  const opener = /\\begin\{([a-zA-Z*]+)\}|\$\$|\$|\\\[|\\\(/g
  opener.lastIndex = from

  let m: RegExpExecArray | null
  while ((m = opener.exec(s))) {
    const start = m.index
    const token = m[0]

    if (token.startsWith('\\begin')) {
      const stack = [m[1]!]
      const environment = /\\(begin|end)\{([a-zA-Z*]+)\}/g
      environment.lastIndex = opener.lastIndex
      let env: RegExpExecArray | null
      while ((env = environment.exec(s))) {
        const [, action, name] = env
        if (action === 'begin') {
          stack.push(name!)
        } else if (stack[stack.length - 1] === name) {
          stack.pop()
          if (!stack.length) {
            return {
              start,
              end: environment.lastIndex,
              latex: s.slice(start, environment.lastIndex),
              display: false,
            }
          }
        }
      }
      // 环境未闭合时继续寻找后面的其他合法定界公式。
      opener.lastIndex = start + token.length
      continue
    }

    const closeToken = token === '$$' ? '$$' : token === '$' ? '$' : token === '\\[' ? '\\]' : '\\)'
    const close = s.indexOf(closeToken, opener.lastIndex)
    if (close < 0 || (token === '$' && s.slice(opener.lastIndex, close).includes('\n'))) {
      opener.lastIndex = start + token.length
      continue
    }
    const end = close + closeToken.length
    return {
      start,
      end,
      latex: s.slice(opener.lastIndex, close),
      display: token === '$$' || token === '\\[',
    }
  }
  return null
}

/** 把 $...$、\\(...\\) 以及 MinerU/译文里无定界符的公式切成文本/公式块 */
export function splitInlineMath(raw: string): RichChunk[] {
  if (!raw) return []
  const out: RichChunk[] = []
  let last = 0
  let delimited: DelimitedMath | null
  while ((delimited = findDelimitedMath(raw, last))) {
    if (delimited.start > last) splitMixedTextMath(raw.slice(last, delimited.start), out)
    out.push({
      kind: 'math',
      text: normalizeSpacedLatex(delimited.latex.trim()),
      display: delimited.display,
    })
    last = delimited.end
  }
  if (last < raw.length) splitMixedTextMath(raw.slice(last), out)
  return mergeAdjacentMath(out).filter((c) => c.text !== '')
}

/** 切分后若相邻 math 块拼接才能通过 KaTeX，则合并 */
function mergeAdjacentMath(chunks: RichChunk[]): RichChunk[] {
  if (chunks.length < 2) return chunks
  const out: RichChunk[] = []
  for (const c of chunks) {
    const prev = out[out.length - 1]
    if (prev?.kind === 'math' && c.kind === 'math') {
      prev.text += c.text
    } else {
      out.push({ ...c })
    }
  }
  return out
}
