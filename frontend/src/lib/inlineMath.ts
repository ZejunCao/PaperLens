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

/** 把 $...$、\\(...\\) 以及 MinerU 无定界符的 \\command 切成文本/公式块 */
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

function isLatexContinue(s: string, j: number): boolean {
  const ch = s[j]
  if (!ch) return false
  if ('\\{}^_'.includes(ch)) return true
  if (ch === ' ' || ch === '\t') {
    const n = s[j + 1]
    if (!n) return false
    if ('\\{}^_'.includes(n)) return true
    if (/[0-9a-zA-Z]/.test(n)) {
      const prev = s[j - 1]
      return prev === '{' || prev === ' ' || prev === '_' || prev === '^' || prev === '}'
    }
  }
  if (/[0-9]/.test(ch)) return true
  if (/[a-zA-Z]/.test(ch)) {
    const prev = s[j - 1]
    return prev === '{' || prev === '_' || prev === '^' || prev === ' ' || prev === '\\'
  }
  return false
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
    let j = bs + 1
    if (j < s.length && /[a-zA-Z]/.test(s[j]!)) {
      while (j < s.length && /[a-zA-Z]/.test(s[j]!)) j++
    } else {
      j++
    }
    while (j < s.length && isLatexContinue(s, j)) j++
    const latex = s.slice(bs, j).trim()
    if (latex.length > 1) out.push({ kind: 'math', text: latex, display: false })
    else pushText(out, s.slice(bs, j))
    i = j
  }
}
