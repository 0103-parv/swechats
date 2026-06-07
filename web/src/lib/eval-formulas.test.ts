import { describe, expect, it } from 'vitest'

import {
  episodeBindingLatex,
  evalFormulas,
  escapeLatexText,
} from './eval-formulas'
import { protectShellDollars } from './streamdown-plugins'

describe('eval formulas', () => {
  it('escapes repo names with slashes and underscores', () => {
    expect(escapeLatexText('org/repo_name')).toBe('org/repo\\_name')
  })

  it('binds episode values into valid latex', () => {
    expect(
      episodeBindingLatex('lightfastai/lightfast', 'session-1', 96),
    ).toContain('\\text{lightfastai/lightfast}')
    expect(
      episodeBindingLatex('lightfastai/lightfast', 'session-1', 96),
    ).toContain(', 96)')
  })

  it('uses system_def notation for causal shape', () => {
    expect(evalFormulas.causalShape).toContain('\\longrightarrow')
  })
})

describe('protectShellDollars', () => {
  it('escapes command substitutions without touching inline math', () => {
    expect(protectShellDollars('run $(npm test) with ${VAR}')).toBe(
      'run \\$(npm test) with \\${VAR}',
    )
    expect(protectShellDollars('let $x = 1$ in prose')).toBe(
      'let $x = 1$ in prose',
    )
  })
})
