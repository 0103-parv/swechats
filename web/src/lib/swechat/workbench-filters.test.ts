import { describe, expect, it } from 'vitest'

import { filterSpecimens, repoOptionsForFilters } from './workbench-filters'
import type { Specimen } from './specimens'
import type { WorkbenchFilters } from './workbench-filters'

describe('workbench filters', () => {
  it('sorts repo options by case count after applying non-repo filters', () => {
    const filters: WorkbenchFilters = {
      unit: 'pushbacks',
      repo: 'repo-c',
      pushback: 'correction',
      quality: 'all',
      q: 'memory',
      starred: 'all',
    }

    expect(repoOptionsForFilters(specimens, filters)).toEqual([
      { repo: 'repo-b', count: 2 },
      { repo: 'repo-a', count: 1 },
      { repo: 'repo-c', count: 1 },
    ])
  })

  it('filters to starred cases when requested', () => {
    const filters: WorkbenchFilters = {
      unit: 'pushbacks',
      repo: 'all',
      pushback: 'all',
      quality: 'all',
      q: '',
      starred: 'starred',
    }

    expect(
      filterSpecimens(specimens, filters, new Set(['case-1', 'case-4'])).map(
        (specimen) => specimen.id,
      ),
    ).toEqual(['case-1', 'case-4'])
  })
})

const specimens: Specimen[] = [
  specimen({
    id: 'case-1',
    repo: 'repo-a',
    pushback: 'correction',
    title: 'memory placement',
  }),
  specimen({
    id: 'case-2',
    repo: 'repo-b',
    pushback: 'correction',
    title: 'memory update',
  }),
  specimen({
    id: 'case-3',
    repo: 'repo-b',
    pushback: 'correction',
    title: 'memory cleanup',
  }),
  specimen({
    id: 'case-4',
    repo: 'repo-c',
    pushback: 'correction',
    title: 'memory review',
  }),
  specimen({
    id: 'case-5',
    repo: 'repo-d',
    pushback: 'rejection',
    title: 'memory mismatch',
  }),
  specimen({
    id: 'case-6',
    repo: 'repo-e',
    pushback: 'correction',
    title: 'other topic',
  }),
]

function specimen({
  id,
  repo,
  pushback,
  title,
}: {
  id: string
  repo: string
  pushback: Specimen['pushback']
  title: string
}): Specimen {
  return {
    id,
    title,
    repo,
    session: `${id}-session`,
    turn: 1,
    unit: 'pushbacks',
    pushback,
    intent: 'coding',
    persona: 'user',
    agent: 'agent',
    codingMode: 'mode',
    priorSessions: 0,
    cleanAttribution: true,
    quality: ['reconstructable'],
    memoryHypothesis: 'memory',
    files: [],
    triad: {
      instruction: title,
      action: 'action',
      pushback: 'pushback',
    },
    transcript: [],
    trajectory: 'No command trace.',
    provenance: {
      baseCommit: 'base',
      checkpoint: 'checkpoint',
      attribution: 'test',
      leakageBoundary: 'test',
    },
    coldRisk: 'risk',
    warmMemory: 'memory',
    judgeQuestion: 'question',
    metrics: {
      turnsBeforePushback: 1,
      filesTouched: 0,
      toolCalls: 0,
      confidence: 1,
    },
  }
}
