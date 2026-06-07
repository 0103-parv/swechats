import type { PushbackKind, QualityTag, Specimen, Unit } from './specimens'

export type PushbackSearch = PushbackKind | 'all'
export type QualitySearch = QualityTag | 'all'
export type StarredSearch = 'all' | 'starred'

export type WorkbenchFilters = {
  unit: Unit
  repo: string
  pushback: PushbackSearch
  quality: QualitySearch
  q: string
  starred: StarredSearch
}

export type RepoOption = {
  repo: string
  count: number
}

export function filterSpecimens(
  specimens: Specimen[],
  filters: WorkbenchFilters,
  starredIds: ReadonlySet<string> = new Set(),
): Specimen[] {
  const query = filters.q.trim().toLowerCase()

  return specimens.filter((item) => {
    if (filters.unit !== 'pushbacks' && item.unit !== filters.unit) {
      return false
    }
    if (filters.repo !== 'all' && item.repo !== filters.repo) {
      return false
    }
    if (filters.pushback !== 'all' && item.pushback !== filters.pushback) {
      return false
    }
    if (filters.quality !== 'all' && !item.quality.includes(filters.quality)) {
      return false
    }
    if (filters.starred === 'starred' && !starredIds.has(item.id)) {
      return false
    }
    if (!query) {
      return true
    }

    return specimenSearchText(item).includes(query)
  })
}

export function repoOptionsForFilters(
  specimens: Specimen[],
  filters: WorkbenchFilters,
  starredIds: ReadonlySet<string> = new Set(),
): RepoOption[] {
  const counts = new Map<string, number>()
  const filtersWithoutRepo = { ...filters, repo: 'all' }

  for (const specimen of filterSpecimens(
    specimens,
    filtersWithoutRepo,
    starredIds,
  )) {
    counts.set(specimen.repo, (counts.get(specimen.repo) ?? 0) + 1)
  }

  return Array.from(counts, ([repo, count]) => ({ repo, count })).sort(
    (left, right) => right.count - left.count || left.repo.localeCompare(right.repo),
  )
}

function specimenSearchText(item: Specimen): string {
  return [
    item.title,
    item.repo,
    item.intent,
    item.triad.instruction,
    item.triad.action,
    item.triad.pushback,
    item.files.map((file) => file.path).join(' '),
  ]
    .join(' ')
    .toLowerCase()
}
