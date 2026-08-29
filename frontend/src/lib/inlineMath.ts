export type RichChunk = { kind: 'text' | 'math'; text: string; display?: boolean }

function pushText(out: RichChunk[], text: string) {
  if (!text) return
  const last = out[out.length - 1]
  if (last?.kind === 'text') last.text += text
  else out.push({ kind: 'text', text })
}

function unwrapDelimited(tok: string): { latex: string; display: boolean } {
  if (tok.startsWith('$$') && tok.endsWith('$$')) return { latex: tok.slice(2, -2), display: true }
  if (tok.startsWith('$') && tok.endsWith('$')) return { latex: tok.slice(1, -1), display: false }
  if (tok.startsWith('\\[') && tok.endsWith('\\]')) return { latex: tok.slice(2, -2), display: true }
  if (tok.startsWith('\\(') && tok.endsWith('\\)')) return { latex: tok.slice(2, -2), display: false }
  return { latex: tok, display: false }
}

/** 把 $...$、\\(...\\) 以及 MinerU/译文里无定界符的 \\command 切成文本/公式块 */
export function splitInlineMath(raw: string): RichChunk[] {
  if (!raw) return []
  const delim =
    /\\begin\{([a-zA-Z*]+)\}[\s\S]*?\\end\{\1\}|\$\$[\s\S]+?\$\$|\$[^$\n]+\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)/g
  const out: RichChunk[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = delim.exec(raw))) {
    if (m.index > last) splitMineruLatex(raw.slice(last, m.index), out)
    const tok = m[0]
    if (tok.startsWith('\\begin')) {
      out.push({ kind: 'math', text: tok, display: true })
    } else {
      const u = unwrapDelimited(tok)
      out.push({ kind: 'math', text: u.latex.trim(), display: u.display })
    }
    last = m.index + tok.length
  }
  if (last < raw.length) splitMineruLatex(raw.slice(last), out)
  return out.filter((c) => c.text !== '')
}

/**
 * 从 `\` 起读一段公式：连续命令、括号、上下标、花括号，直到碰到正文/中文。
 * 避免把 `\left( N^{2} \right)` 拆成 `\l` + `eft(...)`。
 */
function readLatexExpr(s: string, start: number): number {
  let j = start
  let brace = 0
  let sawCmd = false
  while (j < s.length) {
    const ch = s[j]!
    if (ch === '\\') {
      j++
      if (j < s.length && /[a-zA-Z]/.test(s[j]!)) {
        while (j < s.length && /[a-zA-Z]/.test(s[j]!)) j++
        sawCmd = true
        continue
      }
      // \{ \} \, 等
      if (j < s.length) j++
      continue
    }
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
    if (ch === '^' || ch === '_') {
      j++
      continue
    }
    if (ch === ' ' || ch === '\t') {
      const n = s[j + 1]
      if (!n) break
      if (n === '\\' || n === '{' || n === '}' || n === '^' || n === '_') {
        j++
        continue
      }
      if (/[0-9]/.test(n)) {
        j++
        continue
      }
      if (brace > 0 && /[a-zA-Z]/.test(n)) {
        j++
        continue
      }
      if (sawCmd && (n === '(' || n === '[' || n === ')' || n === ']')) {
        j++
        continue
      }
      // `\left( N` / `N ^` 这类公式内部空格
      if (sawCmd && /[a-zA-Z]/.test(n)) {
        const prev = s[j - 1]
        if (prev === '(' || prev === '[' || prev === ')' || prev === ']' || prev === '}' || prev === '\\') {
          j++
          continue
        }
      }
      break
    }
    if (/[0-9]/.test(ch)) {
      j++
      continue
    }
    if ((ch === '(' || ch === '[' || ch === ')' || ch === ']') && sawCmd) {
      j++
      continue
    }
    if (brace > 0 && (/[a-zA-Z.,;:+\-*/=]/.test(ch))) {
      j++
      continue
    }
    // 单字母变量紧跟在命令后：N in \left( N
    if (sawCmd && /[a-zA-Z]/.test(ch) && brace === 0) {
      const prev = s[j - 1]
      if (prev === '(' || prev === '[' || prev === ' ' || prev === '{') {
        j++
        continue
      }
    }
    break
  }
  return j
}

function splitMineruLatex(s: string, out: RichChunk[]) {
  if (!s.includes('\\')) {
    pushText(out, s)
    return
  }
  let i = 0
  while (i < s.length) {
    const bs = s.indexOf('\\', i)
    if (bs < 0) {
      pushText(out, s.slice(i))
      return
    }
    if (bs > i) pushText(out, s.slice(i, bs))
    const end = readLatexExpr(s, bs)
    const latex = s.slice(bs, end).trim()
    if (latex.length > 1) out.push({ kind: 'math', text: latex, display: false })
    else pushText(out, s.slice(bs, end))
    i = end
  }
}
