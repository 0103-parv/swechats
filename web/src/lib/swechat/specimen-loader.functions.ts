import { createServerFn } from '@tanstack/react-start'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import type { ZodError, ZodType } from 'zod'

import { candidatePushbackRowSchema, evalCaseRowSchema } from './schema'
import type {
  ArtifactKind,
  RawCandidatePushbackRow,
  RawEvalCaseRow,
} from './schema'
import type {
  LoadDiagnostic,
  LoadedSpecimenSource,
  LoadSpecimensResult,
  PushbackKind,
  QualityTag,
  Specimen,
  TranscriptEvent,
} from './specimens'

type ArtifactCandidate = {
  kind: ArtifactKind
  id: string
  label: string
  path: string
}

type ParsedArtifact<TRow> = {
  rows: TRow[]
  parsed: number
  skipped: number
  diagnostics: LoadDiagnostic[]
}

const artifactCandidates = [
  {
    id: 'dataset',
    label: 'Full dataset eval cases',
    kind: 'eval-cases',
    path: '../artifacts/eval-cases-dataset.jsonl',
  },
  {
    id: 'entireio-eval',
    label: 'entireio/cli scored smoke',
    kind: 'eval-cases',
    path: '../artifacts/eval-cases-entireio-cli.jsonl',
  },
  {
    id: 'candidate-pushbacks',
    label: 'Raw pushback candidates',
    kind: 'candidate-pushbacks',
    path: '../artifacts/candidate-pushbacks-all.jsonl',
  },
] satisfies ArtifactCandidate[]

export const loadSpecimens = createServerFn({ method: 'GET' }).handler(
  async (): Promise<LoadSpecimensResult> => {
    const diagnostics: LoadDiagnostic[] = []
    const sources: LoadedSpecimenSource[] = []
    let sawArtifactFile = false

    for (const candidate of artifactCandidates) {
      const absolutePath = resolve(process.cwd(), candidate.path)
      if (!existsSync(absolutePath)) {
        diagnostics.push({
          path: candidate.path,
          message: 'Artifact file was not found.',
        })
        continue
      }

      sawArtifactFile = true

      if (candidate.kind === 'eval-cases') {
        const artifact = await readJsonl(
          absolutePath,
          candidate.path,
          evalCaseRowSchema,
        )
        const specimens = artifact.rows.map(evalCaseToSpecimen)

        if (specimens.length > 0) {
          sources.push(loadedResult(candidate, specimens, artifact))
          continue
        }

        diagnostics.push(...artifact.diagnostics)
        continue
      }

      const artifact = await readJsonl(
        absolutePath,
        candidate.path,
        candidatePushbackRowSchema,
      )
      const specimens = artifact.rows.map(candidatePushbackToSpecimen)

      if (specimens.length > 0) {
        sources.push(loadedResult(candidate, specimens, artifact))
        continue
      }

      diagnostics.push(...artifact.diagnostics)
    }

    if (sources.length > 0) {
      const source = sources[0]!

      return {
        sources,
        source,
        specimens: source.specimens,
      }
    }

    return {
      sources: [],
      specimens: [],
      source: {
        id: 'none',
        label: sawArtifactFile ? 'Invalid artifacts' : 'Missing artifacts',
        path: artifactCandidates.map((candidate) => candidate.path).join(', '),
        kind: sawArtifactFile ? 'invalid' : 'missing',
        loaded: 0,
        parsed: 0,
        skipped: diagnostics.length,
        diagnostics,
      },
    }
  },
)

async function readJsonl<TRow>(
  absolutePath: string,
  displayPath: string,
  schema: ZodType<TRow>,
): Promise<ParsedArtifact<TRow>> {
  const file = await readFile(absolutePath, 'utf8')
  const rows: TRow[] = []
  const diagnostics: LoadDiagnostic[] = []
  let parsed = 0
  let skipped = 0

  file.split(/\r?\n/).forEach((rawLine, index) => {
    const line = rawLine.trim()
    if (!line) {
      return
    }

    const lineNumber = index + 1
    let json: unknown

    try {
      json = JSON.parse(line)
    } catch (error) {
      skipped += 1
      diagnostics.push({
        path: displayPath,
        line: lineNumber,
        message: `Invalid JSONL row: ${errorMessage(error)}`,
      })
      return
    }

    const result = schema.safeParse(json)
    if (!result.success) {
      skipped += 1
      diagnostics.push({
        path: displayPath,
        line: lineNumber,
        message: `Artifact schema mismatch: ${zodIssueSummary(result.error)}`,
      })
      return
    }

    parsed += 1
    rows.push(result.data)
  })

  return { rows, parsed, skipped, diagnostics }
}

function loadedResult<TRow>(
  candidate: ArtifactCandidate,
  specimens: Specimen[],
  artifact: ParsedArtifact<TRow>,
): LoadedSpecimenSource {
  return {
    id: candidate.id,
    label: candidate.label,
    path: candidate.path,
    kind: candidate.id === 'dataset' ? 'dataset-eval-cases' : candidate.kind,
    loaded: specimens.length,
    parsed: artifact.parsed,
    skipped: artifact.skipped,
    diagnostics: artifact.diagnostics,
    specimens,
  }
}

function evalCaseToSpecimen(raw: RawEvalCaseRow): Specimen {
  const pushback = normalizePushback(raw.prompt_pushback)
  const files = extractFiles(
    `${raw.i_content}\n${raw.a_content}\n${raw.p_content}`,
  )
  const quality = inferQuality({
    pushbackText: raw.p_content,
    fileCount: files.length,
    priorSessions: raw.eligible_prior_sessions,
    hasAction: true,
    hasInstruction: true,
  })
  const title = titleFrom(raw.p_content, raw.i_content)

  const transcript =
    raw.chat_window && raw.chat_window.length > 0
      ? raw.chat_window.map((turn) =>
          chatWindowToTranscriptEvent(turn, pushback),
        )
      : compactTriadTranscript(raw, pushback)

  return {
    id: raw.case_id,
    title,
    repo: raw.repo_id,
    session: shorten(raw.session_id, 8),
    turn: raw.p_turn_number,
    unit: 'pushbacks',
    pushback,
    intent: raw.prompt_intent,
    persona: raw.user_id ? `user ${raw.user_id}` : 'unknown user',
    agent: raw.agent,
    codingMode: 'I/A/P eval artifact',
    priorSessions: raw.eligible_prior_sessions,
    cleanAttribution: true,
    quality,
    memoryHypothesis: buildMemoryHypothesis(
      raw.repo_id,
      raw.eligible_prior_sessions,
    ),
    files,
    triad: {
      instruction: truncate(raw.i_content, 1400),
      action: truncate(raw.a_content, 1400),
      pushback: truncate(raw.p_content, 1400),
    },
    transcript,
    trajectory: extractTrajectory(
      `${raw.i_content}\n${raw.a_content}\n${raw.p_content}`,
    ),
    provenance: {
      baseCommit: shorten(raw.checkpoint_pk, 18),
      checkpoint: raw.checkpoint_pk,
      attribution: 'I/A/P eval-case artifact',
      leakageBoundary: `Use only ${raw.repo_id} sessions before repo_session_index ${raw.repo_session_index}; hold out session ${raw.session_id}.`,
    },
    coldRisk: `Cold agent may repeat the flaw named by this ${pushback} because no repo-local memory is injected.`,
    warmMemory: buildWarmMemory(raw.p_content, files),
    judgeQuestion: `Does the regenerated answer still exhibit this flaw: "${truncate(raw.p_content, 220)}"?`,
    metrics: {
      turnsBeforePushback: Math.max(0, raw.p_turn_number - raw.i_turn_number),
      filesTouched: files.length,
      toolCalls: Math.max(0, raw.a_turn_number - raw.i_turn_number - 1),
      confidence: quality.includes('demo-worthy') ? 0.74 : 0.58,
    },
  }
}

function compactTriadTranscript(
  raw: RawEvalCaseRow,
  pushback: PushbackKind,
): TranscriptEvent[] {
  return [
    {
      symbol: 'U',
      role: 'user',
      label: `Instruction ${raw.i_turn_id}`,
      body: truncate(raw.i_content, 1200),
      marker: 'I',
      turn: raw.i_turn_number,
    },
    {
      symbol: 'A',
      role: 'assistant',
      label: `Action on trial ${raw.a_turn_id}`,
      body: truncate(raw.a_content, 1200),
      marker: 'A',
      turn: raw.a_turn_number,
    },
    {
      symbol: pushback === 'rejection' ? 'R' : 'P',
      role: 'user',
      label: `Held-out ${pushback} ${raw.p_turn_id}`,
      body: truncate(raw.p_content, 1200),
      marker: 'P',
      turn: raw.p_turn_number,
    },
  ]
}

function chatWindowToTranscriptEvent(
  turn: NonNullable<RawEvalCaseRow['chat_window']>[number],
  pushback: PushbackKind,
): TranscriptEvent {
  const marker = turn.marker ?? null
  const role =
    turn.role === 'assistant'
      ? 'assistant'
      : turn.role === 'user'
        ? 'user'
        : 'system'
  const symbol =
    marker === 'I'
      ? 'U'
      : marker === 'A'
        ? 'A'
        : marker === 'P'
          ? pushback === 'rejection'
            ? 'R'
            : 'P'
          : role === 'assistant'
            ? 'A'
            : role === 'user'
              ? 'U'
              : '?'
  const label =
    marker === 'I'
      ? `Instruction turn ${turn.turn_number}`
      : marker === 'A'
        ? `Action on trial turn ${turn.turn_number}`
        : marker === 'P'
          ? `Held-out ${pushback} turn ${turn.turn_number}`
          : `Turn ${turn.turn_number}`

  return {
    symbol,
    role,
    label,
    body: truncate(turn.content, 1800),
    marker,
    turn: turn.turn_number,
  }
}

function candidatePushbackToSpecimen(raw: RawCandidatePushbackRow): Specimen {
  const pushback = normalizePushback(raw.prompt_pushback)
  const files = extractFiles(raw.content)
  const quality = inferQuality({
    pushbackText: raw.content,
    fileCount: files.length,
    priorSessions: 0,
    hasAction: false,
    hasInstruction: false,
  })
  const actionPlaceholder =
    'This candidate-pushbacks artifact does not include the prior assistant action. Join it against conversations.parquet before scoring an I/A/P counterfactual.'

  return {
    id: `${raw.turn_id}:${raw.prompt_pushback}`,
    title: titleFrom(raw.content, raw.content),
    repo: raw.repo_id,
    session: shorten(raw.session_id, 8),
    turn: raw.turn_number,
    unit: 'pushbacks',
    pushback,
    intent: raw.prompt_intent,
    persona: 'unknown user',
    agent: 'unknown agent',
    codingMode: 'pushback candidate artifact',
    priorSessions: 0,
    cleanAttribution: false,
    quality,
    memoryHypothesis:
      'This row is a real pushback candidate. It needs session joins to recover I/A and chronological memory boundaries before it becomes an eval case.',
    files,
    triad: {
      instruction:
        'Not present in candidate-pushbacks-all.jsonl; load the previous user_prompt for this session to recover I.',
      action: actionPlaceholder,
      pushback: truncate(raw.content, 1400),
    },
    transcript: [
      {
        symbol: '!',
        role: 'user',
        label: `${pushback} ${raw.turn_id}`,
        body: truncate(raw.content, 700),
      },
      {
        symbol: 'E',
        role: 'system',
        label: 'Loader note',
        body: actionPlaceholder,
      },
    ],
    trajectory: extractTrajectory(raw.content),
    provenance: {
      baseCommit: shorten(raw.checkpoint_pk, 18),
      checkpoint: raw.checkpoint_pk,
      attribution:
        'candidate-pushbacks artifact; no assistant action or prior instruction attached',
      leakageBoundary: `Use only earlier ${raw.repo_id} sessions once session chronology is joined; timestamp ${raw.timestamp ?? 'missing'}.`,
    },
    coldRisk:
      'Not scoreable yet: the row names a real correction, but the action on trial has not been joined.',
    warmMemory: buildWarmMemory(raw.content, files),
    judgeQuestion: `After joining I/A, does the regenerated answer still exhibit this flaw: "${truncate(raw.content, 220)}"?`,
    metrics: {
      turnsBeforePushback: 0,
      filesTouched: files.length,
      toolCalls: 0,
      confidence: quality.includes('demo-worthy') ? 0.48 : 0.32,
    },
  }
}

function inferQuality({
  pushbackText,
  fileCount,
  priorSessions,
  hasAction,
  hasInstruction,
}: {
  pushbackText: string
  fileCount: number
  priorSessions: number
  hasAction: boolean
  hasInstruction: boolean
}): QualityTag[] {
  const tags: QualityTag[] = []
  const lower = pushbackText.toLowerCase()

  if (hasAction && hasInstruction) {
    tags.push('reconstructable')
  }
  if (priorSessions >= 10) {
    tags.push('clean prior memory')
  }
  if (
    fileCount > 0 ||
    /wrong|format|path|test|hook|commit|config/.test(lower)
  ) {
    tags.push('objective repo gotcha')
  }
  if (/\[image|screenshot|browser|ui|visual/.test(lower)) {
    tags.push('needs runtime')
  }
  if (/\b(prefer|style|rename|wording|tone|shorter|longer)\b/.test(lower)) {
    tags.push('user preference')
  }
  if (/\b(harness|fixture|flake|timeout|ci environment|setup)\b/.test(lower)) {
    tags.push('harness issue')
  }
  if (pushbackText.length < 40) {
    tags.push('too vague')
  }
  if (
    hasAction &&
    hasInstruction &&
    priorSessions >= 20 &&
    !tags.includes('needs runtime')
  ) {
    tags.push('demo-worthy')
  }

  return tags.length > 0 ? tags : ['too vague']
}

function extractFiles(text: string): Specimen['files'] {
  const matches = text.match(
    /(?:^|\s|`)([\w./-]+\.(?:go|ts|tsx|js|jsx|py|md|json|jsonl|yaml|yml|toml|sh|rs|css))/g,
  )
  const paths = Array.from(
    new Set((matches ?? []).map((match) => match.trim().replace(/^`/, ''))),
  ).filter(Boolean)

  return paths.slice(0, 8).map((path) => ({
    path,
    status: 'modified',
    additions: 0,
    deletions: 0,
  }))
}

function extractTrajectory(text: string): string {
  const commandLines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) =>
      /^(?:\$|bun |uv |go |mise |npm |pnpm |rg |git |pytest |cargo |scripts\/)/.test(
        line,
      ),
    )
    .slice(0, 8)

  if (commandLines.length > 0) {
    return commandLines.join('\n')
  }

  return 'No command trace was present in this artifact row.'
}

function buildMemoryHypothesis(repo: string, priorSessions: number): string {
  return `If earlier ${repo} sessions contain the same convention, durable memory should make the agent avoid this correction before seeing the held-out pushback. Eligible prior sessions: ${priorSessions}.`
}

function buildWarmMemory(
  pushbackText: string,
  files: Specimen['files'],
): string {
  const scopedFiles = files.map((file) => file.path).join(', ')
  const scope = scopedFiles ? ` Scope: ${scopedFiles}.` : ''

  return `Candidate memory should encode the repo convention behind the correction, not the exact held-out answer.${scope} Correction signal: ${truncate(pushbackText, 280)}`
}

function normalizePushback(value: string): PushbackKind {
  if (value === 'rejection') {
    return 'rejection'
  }
  if (value === 'correction') {
    return 'correction'
  }
  return 'clarification'
}

function titleFrom(pushbackText: string, instruction: string): string {
  const source =
    firstMeaningfulLine(pushbackText) ?? firstMeaningfulLine(instruction)
  return truncate(source ?? 'Untitled pushback case', 86)
}

function firstMeaningfulLine(value: string): string | null {
  return (
    value
      .split(/\r?\n/)
      .map((line) => line.replace(/^#+\s*/, '').trim())
      .find((line) => line.length > 0) ?? null
  )
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value
  }

  return `${value.slice(0, maxLength - 3).trimEnd()}...`
}

function shorten(value: string, length: number): string {
  return value.length > length ? value.slice(0, length) : value
}

function zodIssueSummary(error: ZodError): string {
  return error.issues
    .slice(0, 3)
    .map((issue) => `${issue.path.join('.') || '<row>'}: ${issue.message}`)
    .join('; ')
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'unknown error'
}
