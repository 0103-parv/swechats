export function escapeLatexText(value: string): string {
  return value.replace(/[\\%&#_{}]/g, (char) => `\\${char}`)
}

export function episodeBindingLatex(
  repo: string,
  session: string,
  turn: number,
): string {
  return `e := (r, s, i) = (\\text{${escapeLatexText(repo)}}, \\text{${escapeLatexText(session)}}, ${turn})`
}

export const evalFormulas = {
  causalShape: String.raw`(h_e, w_e, u_e) \longrightarrow a_e \longrightarrow p_e`,
  coldContext: String.raw`x_e^0 := (w_e, h_e, u_e)`,
  warmContext: String.raw`x_e^k := (w_e \oplus k_e, h_e, u_e)`,
  memoryCorpus: String.raw`d_e := \{S_{r,s'} : s' < s\}`,
  memoryLearner: String.raw`k_e := L(d_e)`,
  oraclePacket: String.raw`o_e := (u_e, a_e, p_e, \mathrm{tail}_e, \Delta_e)`,
  rubric: String.raw`\mathcal{R}_e := G(o_e)`,
  criterion: String.raw`c_{e,j} : \mathsf{Action} \rightarrow \{0, 1\}`,
  coldCandidate: String.raw`\hat{a}_e^0 := A(x_e^0)`,
  warmCandidate: String.raw`\hat{a}_e^k := A(x_e^k)`,
  score: String.raw`\operatorname{score}_e^z := \frac{1}{|\mathcal{R}_e|} \sum_{c \in \mathcal{R}_e} J(c, \hat{a}_e^z)`,
  lift: String.raw`\operatorname{lift}_e := \operatorname{score}_e^k - \operatorname{score}_e^0`,
} as const
