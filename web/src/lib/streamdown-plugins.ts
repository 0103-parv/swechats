import { cjk } from '@streamdown/cjk'
import { code } from '@streamdown/code'
import { createMathPlugin } from '@streamdown/math'
import { mermaid } from '@streamdown/mermaid'

export const streamdownPlugins = {
  cjk,
  code,
  math: createMathPlugin({ singleDollarTextMath: true }),
  mermaid,
}

/** Backslash-escape unambiguous shell expansions before inline math parsing. */
export function protectShellDollars(text: string): string {
  return text.replace(/\$(?=[({])/g, '\\$')
}
