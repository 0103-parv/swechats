export type Unit = 'pushbacks' | 'sessions' | 'turns' | 'tools' | 'commits'

export type PushbackKind = 'correction' | 'rejection' | 'clarification'

export type QualityTag =
  | 'objective repo gotcha'
  | 'user preference'
  | 'too vague'
  | 'needs runtime'
  | 'harness issue'
  | 'reconstructable'
  | 'clean prior memory'
  | 'demo-worthy'

export type TranscriptEvent = {
  symbol: 'U' | 'A' | 'P' | 'R' | 'E' | 'B' | 'G' | '?' | '!' | 'C'
  role: 'user' | 'assistant' | 'system'
  label: string
  body: string
  marker?: 'I' | 'A' | 'P' | null
  turn?: number
}

export type Specimen = {
  id: string
  title: string
  repo: string
  session: string
  turn: number
  unit: Unit
  pushback: PushbackKind
  intent: string
  persona: string
  agent: string
  codingMode: string
  priorSessions: number
  cleanAttribution: boolean
  quality: QualityTag[]
  memoryHypothesis: string
  files: Array<{
    path: string
    status: 'added' | 'modified' | 'deleted' | 'renamed'
    additions: number
    deletions: number
  }>
  triad: {
    instruction: string
    action: string
    pushback: string
  }
  transcript: TranscriptEvent[]
  trajectory: string
  provenance: {
    baseCommit: string
    checkpoint: string
    attribution: string
    leakageBoundary: string
  }
  coldRisk: string
  warmMemory: string
  judgeQuestion: string
  metrics: {
    turnsBeforePushback: number
    filesTouched: number
    toolCalls: number
    confidence: number
  }
}

export const units: Array<{ value: Unit; label: string }> = [
  { value: 'pushbacks', label: 'Pushbacks' },
  { value: 'sessions', label: 'Sessions' },
  { value: 'turns', label: 'Turns' },
  { value: 'tools', label: 'Tools' },
  { value: 'commits', label: 'Commits' },
]

export const qualityTags: QualityTag[] = [
  'objective repo gotcha',
  'user preference',
  'too vague',
  'needs runtime',
  'harness issue',
  'reconstructable',
  'clean prior memory',
  'demo-worthy',
]

export type SpecimenSourceKind =
  | 'dataset-eval-cases'
  | 'eval-cases'
  | 'candidate-pushbacks'
  | 'missing'
  | 'invalid'

export type LoadDiagnostic = {
  path: string
  message: string
  line?: number
}

export type SpecimenSource = {
  id: string
  label: string
  path: string
  kind: SpecimenSourceKind
  loaded: number
  parsed: number
  skipped: number
  diagnostics: LoadDiagnostic[]
}

export type LoadedSpecimenSource = SpecimenSource & {
  specimens: Specimen[]
}

export type LoadSpecimensResult = {
  sources: LoadedSpecimenSource[]
  specimens: Specimen[]
  source: SpecimenSource
}
