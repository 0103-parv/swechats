import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from '#/components/ai-elements/conversation'
import {
  Message,
  MessageContent,
  MessageResponse,
} from '#/components/ai-elements/message'
import { FormulaBlock } from '#/components/formula-block'
import { episodeBindingLatex, evalFormulas } from '#/lib/eval-formulas'
import { Terminal } from '#/components/ai-elements/terminal'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '#/components/ui/card'
import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'
import { ScrollArea } from '#/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '#/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '#/components/ui/tabs'
import { Textarea } from '#/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '#/components/ui/toggle-group'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '#/components/ui/tooltip'
import { cn } from '#/lib/utils'
import { loadSpecimens } from '#/lib/swechat/specimen-loader.functions'
import { qualityTags, units } from '#/lib/swechat/specimens'
import type {
  QualityTag,
  Specimen,
  LoadedSpecimenSource,
  TranscriptEvent,
  Unit,
} from '#/lib/swechat/specimens'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import {
  CheckCircle2,
  Brain,
  Database,
  FileCode2,
  Filter,
  FlaskConical,
  GitBranch,
  History,
  ListChecks,
  LockKeyhole,
  MemoryStick,
  Play,
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
  Table2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  filterSpecimens,
  repoOptionsForFilters,
} from '#/lib/swechat/workbench-filters'
import type {
  PushbackSearch,
  QualitySearch,
  RepoOption,
  StarredSearch,
  WorkbenchFilters,
} from '#/lib/swechat/workbench-filters'

type SearchState = {
  source: string
  unit: Unit
  repo: string
  pushback: PushbackSearch
  quality: QualitySearch
  starred: StarredSearch
  q: string
  selected: string | undefined
}

type UnitCounts = Record<Unit, number>
const starredStorageKey = 'swechat-workbench-starred-cases'

export const Route = createFileRoute('/')({
  validateSearch: (search): SearchState => ({
    source: parseString(search.source, 'dataset'),
    unit: parseUnit(search.unit),
    repo: parseString(search.repo, 'all'),
    pushback: parsePushback(search.pushback),
    quality: parseQuality(search.quality),
    starred: parseStarred(search.starred),
    q: parseString(search.q, ''),
    selected: parseOptionalString(search.selected),
  }),
  loader: () => loadSpecimens(),
  component: Home,
})

function Home() {
  const data = Route.useLoaderData()
  const search = Route.useSearch()
  const navigate = useNavigate({ from: '/' })
  const activeLoadedSource =
    data.sources.find((source) => source.id === search.source) ??
    data.sources[0]
  const activeSource = activeLoadedSource ?? data.source
  const specimens: Specimen[] = activeLoadedSource?.specimens ?? data.specimens
  const unitCounts = countUnits(specimens)
  const [starredCaseKeys, setStarredCaseKeys] = useState<Set<string>>(
    () => new Set(),
  )
  const [starsLoaded, setStarsLoaded] = useState(false)
  const starredIds = useMemo(
    () =>
      new Set(
        specimens
          .filter((specimen) =>
            starredCaseKeys.has(starStorageKey(activeSource.id, specimen.id)),
          )
          .map((specimen) => specimen.id),
      ),
    [activeSource.id, specimens, starredCaseKeys],
  )
  const filters: WorkbenchFilters = {
    unit: search.unit,
    repo: search.repo,
    pushback: search.pushback,
    quality: search.quality,
    starred: search.starred,
    q: search.q,
  }
  const repos = repoOptionsForFilters(specimens, filters, starredIds)
  const filtered = filterSpecimens(specimens, filters, starredIds)
  const selected =
    filtered.find((item) => item.id === search.selected) || filtered[0]

  useEffect(() => {
    setStarredCaseKeys(readStarredCaseKeys())
    setStarsLoaded(true)
  }, [])

  useEffect(() => {
    if (!starsLoaded) {
      return
    }

    writeStarredCaseKeys(starredCaseKeys)
  }, [starredCaseKeys, starsLoaded])

  const patchSearch = (patch: Partial<SearchState>) =>
    navigate({
      search: (current) => ({
        ...current,
        ...patch,
        selected: patch.selected ?? current.selected,
      }),
    })

  const toggleStar = (specimen: Specimen) => {
    const key = starStorageKey(activeSource.id, specimen.id)
    setStarredCaseKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <main className="flex h-dvh min-h-[720px] flex-col bg-background text-foreground">
      <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg border bg-muted">
            <Database className="size-4" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate font-heading text-lg font-medium">
              SWE-chat episode eval workbench
            </h1>
            <p className="truncate text-muted-foreground text-xs">
              {activeSource.loaded} cases from {activeSource.path}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="secondary">{activeSource.kind}</Badge>
          <Badge variant="outline">{filtered.length} visible</Badge>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(340px,420px)_minmax(0,1fr)]">
        <FilterRail
          quality={search.quality}
          pushback={search.pushback}
          query={search.q}
          repo={search.repo}
          repos={repos}
          source={activeSource.id}
          sources={data.sources}
          starred={search.starred}
          starredCount={starredIds.size}
          unitCounts={unitCounts}
          unit={search.unit}
          onChange={patchSearch}
        />
        <CandidateList
          cases={filtered}
          selectedId={selected?.id}
          starredIds={starredIds}
          onSelect={(id) => patchSearch({ selected: id })}
          onToggleStar={toggleStar}
        />
        <DetailPane
          isStarred={selected ? starredIds.has(selected.id) : false}
          specimen={selected}
          onToggleStar={selected ? () => toggleStar(selected) : undefined}
        />
      </div>
    </main>
  )
}

function FilterRail({
  source,
  sources,
  unit,
  unitCounts,
  repo,
  repos,
  pushback,
  quality,
  starred,
  starredCount,
  query,
  onChange,
}: {
  source: string
  sources: LoadedSpecimenSource[]
  unit: Unit
  unitCounts: UnitCounts
  repo: string
  repos: RepoOption[]
  pushback: PushbackSearch
  quality: QualitySearch
  starred: StarredSearch
  starredCount: number
  query: string
  onChange: (patch: Partial<SearchState>) => void
}) {
  return (
    <aside className="flex min-h-0 flex-col gap-5 border-r bg-muted/25 p-4">
      <section className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-muted-foreground text-xs font-medium">
          <Database className="size-3.5" />
          Source
        </div>
        <LabeledSelect
          label="Artifact"
          value={source}
          onChange={(value) =>
            onChange({
              source: value,
              repo: 'all',
              pushback: 'all',
              quality: 'all',
              q: '',
              selected: undefined,
            })
          }
        >
          {sources.length === 0 ? (
            <SelectItem value="none">No artifacts</SelectItem>
          ) : (
            sources.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.label} ({item.loaded})
              </SelectItem>
            ))
          )}
        </LabeledSelect>
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-muted-foreground text-xs font-medium">
          <Table2 className="size-3.5" />
          Unit
        </div>
        <ToggleGroup
          className="grid w-full grid-cols-2"
          type="single"
          value={unit}
          variant="outline"
          onValueChange={(value) => {
            if (value) {
              onChange({ unit: value as Unit, selected: undefined })
            }
          }}
        >
          {units.slice(0, 4).map((item) => (
            <ToggleGroupItem
              disabled={unitCounts[item.value] === 0}
              key={item.value}
              value={item.value}
            >
              {item.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-muted-foreground text-xs font-medium">
          <Filter className="size-3.5" />
          Filters
        </div>
        <LabeledSelect
          label="Repo"
          value={repo}
          onChange={(value) => onChange({ repo: value, selected: undefined })}
        >
          <SelectItem value="all">All repos</SelectItem>
          {repos.map((item) => (
            <SelectItem key={item.repo} value={item.repo}>
              {item.repo} ({item.count})
            </SelectItem>
          ))}
        </LabeledSelect>
        <LabeledSelect
          label="Pushback"
          value={pushback}
          onChange={(value) =>
            onChange({ pushback: value as PushbackSearch, selected: undefined })
          }
        >
          <SelectItem value="all">All pushbacks</SelectItem>
          <SelectItem value="correction">Corrections</SelectItem>
          <SelectItem value="rejection">Rejections</SelectItem>
          <SelectItem value="clarification">Clarifications</SelectItem>
        </LabeledSelect>
        <LabeledSelect
          label="Quality"
          value={quality}
          onChange={(value) =>
            onChange({ quality: value as QualitySearch, selected: undefined })
          }
        >
          <SelectItem value="all">Any quality</SelectItem>
          {qualityTags.map((tag) => (
            <SelectItem key={tag} value={tag}>
              {tag}
            </SelectItem>
          ))}
        </LabeledSelect>
        <div className="flex flex-col gap-1.5">
          <Label className="text-xs">Stars</Label>
          <ToggleGroup
            className="grid w-full grid-cols-2"
            type="single"
            value={starred}
            variant="outline"
            onValueChange={(value) => {
              if (value) {
                onChange({
                  starred: value as StarredSearch,
                  selected: undefined,
                })
              }
            }}
          >
            <ToggleGroupItem value="all">All</ToggleGroupItem>
            <ToggleGroupItem value="starred">
              Starred ({starredCount})
            </ToggleGroupItem>
          </ToggleGroup>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <Label className="text-xs" htmlFor="case-search">
          Search text
        </Label>
        <div className="relative">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-3.5 text-muted-foreground" />
          <Input
            className="pl-8"
            id="case-search"
            placeholder="lock, path, hook..."
            value={query}
            onChange={(event) =>
              onChange({ q: event.target.value, selected: undefined })
            }
          />
        </div>
      </section>

      <section className="mt-auto flex flex-col gap-2 rounded-lg border bg-background p-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <ShieldCheck className="size-4" />
          Leakage firewall
        </div>
        <p className="text-muted-foreground text-xs leading-5">
          Candidate agents see only x_e. Rubric generation sees o_e. Memory
          learning sees prior same-repo sessions, never the held-out episode.
        </p>
      </section>
    </aside>
  )
}

function LabeledSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>{children}</SelectGroup>
        </SelectContent>
      </Select>
    </div>
  )
}

function StarButton({
  isStarred,
  label,
  onClick,
}: {
  isStarred: boolean
  label: string
  onClick: React.MouseEventHandler<HTMLButtonElement>
}) {
  return (
    <Button
      aria-label={label}
      className="size-7 shrink-0"
      size="icon"
      type="button"
      variant="ghost"
      onClick={onClick}
    >
      <Star
        className={cn('size-4', isStarred && 'fill-current text-amber-500')}
      />
    </Button>
  )
}

function CandidateList({
  cases,
  selectedId,
  starredIds,
  onSelect,
  onToggleStar,
}: {
  cases: Specimen[]
  selectedId: string | undefined
  starredIds: ReadonlySet<string>
  onSelect: (id: string) => void
  onToggleStar: (specimen: Specimen) => void
}) {
  return (
    <section className="flex min-h-0 flex-col border-r">
      <div className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <div className="font-medium text-sm">Episodes</div>
        <Badge variant="outline">{cases.length}</Badge>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-3 p-3">
          {cases.length === 0 && (
            <div className="rounded-lg border border-dashed p-4 text-muted-foreground text-sm leading-6">
              No candidates match these filters.
            </div>
          )}
          {cases.map((item) => (
            <EpisodeListItem
              item={item}
              key={item.id}
              selectedId={selectedId}
              isStarred={starredIds.has(item.id)}
              onSelect={onSelect}
              onToggleStar={onToggleStar}
            />
          ))}
        </div>
      </ScrollArea>
    </section>
  )
}

function EpisodeListItem({
  item,
  selectedId,
  isStarred,
  onSelect,
  onToggleStar,
}: {
  item: Specimen
  selectedId: string | undefined
  isStarred: boolean
  onSelect: (id: string) => void
  onToggleStar: (specimen: Specimen) => void
}) {
  const episode = episodeModel(item)

  return (
    <article
      className="cursor-pointer text-left"
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect(item.id)
        }
      }}
      onClick={() => onSelect(item.id)}
    >
      <Card
        className={cn(
          'rounded-lg py-3 transition-colors hover:bg-muted/35',
          selectedId === item.id && 'bg-muted/60 ring-primary/35',
        )}
        size="sm"
      >
        <CardHeader className="px-3">
          <div className="flex min-w-0 items-start gap-2">
            <CardTitle className="line-clamp-2 flex-1 text-sm">
              {item.title}
            </CardTitle>
            <StarButton
              isStarred={isStarred}
              label={isStarred ? 'Unstar episode' : 'Star episode'}
              onClick={(event) => {
                event.stopPropagation()
                onToggleStar(item)
              }}
            />
          </div>
          <CardDescription className="flex min-w-0 items-center gap-2 text-xs">
            <GitBranch className="size-3 shrink-0" />
            <span className="truncate">
              e = ({episode.repo}, {episode.session}, {episode.actionTurn})
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 px-3">
          <div className="flex flex-wrap gap-1.5">
            {isStarred && <Badge variant="default">Starred</Badge>}
            <Badge variant="secondary">{item.pushback}</Badge>
            <Badge variant="outline">{item.intent}</Badge>
            <Badge variant="outline">{item.priorSessions} prior</Badge>
          </div>
          <p className="line-clamp-3 text-muted-foreground text-xs leading-5">
            {item.triad.pushback}
          </p>
        </CardContent>
      </Card>
    </article>
  )
}

function DetailPane({
  specimen,
  isStarred,
  onToggleStar,
}: {
  specimen: Specimen | undefined
  isStarred: boolean
  onToggleStar: (() => void) | undefined
}) {
  if (!specimen) {
    return (
      <section className="grid min-h-0 place-items-center text-muted-foreground text-sm">
        No episode selected.
      </section>
    )
  }

  const episode = episodeModel(specimen)

  return (
    <section className="flex min-h-0 flex-col">
      <div className="flex min-h-16 shrink-0 items-center justify-between gap-3 border-b px-5 py-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate font-heading text-base font-medium">
              Pushback episode e
            </h2>
            <Badge variant="secondary">{specimen.pushback}</Badge>
            <Badge variant="outline">{specimen.intent}</Badge>
          </div>
          <p className="mt-1 truncate font-mono text-muted-foreground text-xs">
            e = ({episode.repo}, {episode.session}, {episode.actionTurn})
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="outline" onClick={onToggleStar}>
            <Star
              className={cn(
                'size-4',
                isStarred && 'fill-current text-amber-500',
              )}
              data-icon="inline-start"
            />
            {isStarred ? 'Starred' : 'Star'}
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="sm" variant="outline">
                <ListChecks data-icon="inline-start" />
                Score episode
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Run A(x_e^0), A(x_e^k), then judge against R_e.
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      <Tabs className="flex min-h-0 flex-1 flex-col" defaultValue="episode">
        <div className="border-b px-5 py-2">
          <TabsList className="h-auto flex-wrap justify-start">
            <TabsTrigger value="episode">Episode</TabsTrigger>
            <TabsTrigger value="reentry">Re-entry</TabsTrigger>
            <TabsTrigger value="memory">Memory</TabsTrigger>
            <TabsTrigger value="oracle">Oracle</TabsTrigger>
            <TabsTrigger value="rubric">Rubric</TabsTrigger>
            <TabsTrigger value="runs">Runs</TabsTrigger>
            <TabsTrigger value="scores">Scores</TabsTrigger>
            <TabsTrigger value="raw">Raw</TabsTrigger>
          </TabsList>
        </div>

        <ScrollArea className="min-h-0 flex-1">
          <TabsContent className="m-0 p-5" value="episode">
            <EpisodeTab episode={episode} specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="reentry">
            <ReentryTab episode={episode} specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="memory">
            <MemoryTab episode={episode} specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="oracle">
            <OracleTab specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="rubric">
            <RubricTab specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="runs">
            <RunsTab specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="scores">
            <ScoresTab specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="raw">
            <Textarea
              className="min-h-[560px] font-mono text-xs"
              readOnly
              value={JSON.stringify(specimen, null, 2)}
            />
          </TabsContent>
        </ScrollArea>
      </Tabs>
    </section>
  )
}

type EpisodeModel = {
  repo: string
  session: string
  instructionTurn: number
  actionTurn: number
  pushbackTurn: number
  historyEvents: TranscriptEvent[]
  tailEvents: TranscriptEvent[]
}

function EpisodeTab({
  episode,
  specimen,
}: {
  episode: EpisodeModel
  specimen: Specimen
}) {
  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-4 rounded-lg border p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">e</Badge>
          <h3 className="font-medium text-sm">
            One held-out pushback episode
          </h3>
        </div>
        <FormulaBlock
          latex={episodeBindingLatex(
            episode.repo,
            episode.session,
            episode.actionTurn,
          )}
        />
        <div className="grid gap-3 md:grid-cols-3">
          <ObjectPanel
            label="u_e"
            title="Trigger instruction"
            text={specimen.triad.instruction}
          />
          <ObjectPanel
            label="a_e"
            title="Logged action on trial"
            text={specimen.triad.action}
          />
          <ObjectPanel
            label="p_e"
            title="Observed pushback"
            text={specimen.triad.pushback}
            tone="danger"
          />
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2 font-medium text-sm">
          <History className="size-4" />
          Annotated episode timeline
        </div>
        <ChatTranscript specimen={specimen} />
      </section>
    </div>
  )
}

function ReentryTab({
  episode,
  specimen,
}: {
  episode: EpisodeModel
  specimen: Specimen
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PipelineCard icon={<Play className="size-4" />} title="Cold context">
        <FormulaBlock latex={evalFormulas.coldContext} />
        <ObjectPanel
          label="w_e"
          title="Workspace state"
          text={`Checkpoint ${specimen.provenance.checkpoint}`}
        />
        <ObjectPanel
          label="h_e"
          title="Available history prefix"
          text={historySummary(episode)}
        />
        <ObjectPanel
          label="u_e"
          title="Trigger instruction"
          text={specimen.triad.instruction}
        />
      </PipelineCard>

      <PipelineCard
        icon={<MemoryStick className="size-4" />}
        title="Warm context"
      >
        <FormulaBlock latex={evalFormulas.warmContext} />
        <ObjectPanel
          label="w_e ⊕ k_e"
          title="Workspace with memory overlay"
          text="Not materialized yet. This is where generated AGENTS.md / skills would be inserted before rerunning the candidate agent."
          tone="muted"
        />
        <ObjectPanel
          label="h_e"
          title="Same history prefix"
          text="Identical to cold. The counterfactual intervention is the memory overlay, not a different conversation."
          tone="muted"
        />
        <ObjectPanel
          label="u_e"
          title="Same trigger instruction"
          text={specimen.triad.instruction}
        />
      </PipelineCard>

      <section className="xl:col-span-2">
        <LeakageFirewall />
      </section>
    </div>
  )
}

function MemoryTab({
  episode,
  specimen,
}: {
  episode: EpisodeModel
  specimen: Specimen
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <PipelineCard icon={<Brain className="size-4" />} title="Memory learner">
        <FormulaBlock latex={evalFormulas.memoryCorpus} />
        <FormulaBlock latex={evalFormulas.memoryLearner} />
        <div className="grid gap-3 md:grid-cols-2">
          <ObjectPanel
            label="d_e"
            title="Memory corpus"
            text={`${specimen.priorSessions} eligible earlier sessions in ${episode.repo}. The held-out session is excluded.`}
          />
          <ObjectPanel
            label="k_e"
            title="Memory artifact"
            text="Not generated yet for this episode."
            tone="muted"
          />
        </div>
      </PipelineCard>

      <aside className="flex flex-col gap-4">
        <PipelineCard
          icon={<Sparkles className="size-4" />}
          title="Memory hypothesis"
        >
          <p className="text-muted-foreground text-sm leading-6">
            {specimen.memoryHypothesis}
          </p>
        </PipelineCard>
        <PipelineCard
          icon={<FileCode2 className="size-4" />}
          title="Candidate memory shape"
        >
          <p className="text-muted-foreground text-sm leading-6">
            {specimen.warmMemory}
          </p>
        </PipelineCard>
      </aside>
    </div>
  )
}

function ChatTranscript({ specimen }: { specimen: Specimen }) {
  return (
    <Conversation className="h-[620px] rounded-lg border">
      <ConversationContent className="gap-5">
        {specimen.transcript.map((event) => (
          <Message
            className={cn(
              event.marker === 'P' && 'rounded-lg ring-2 ring-destructive/25',
              event.marker === 'A' && 'rounded-lg ring-2 ring-primary/20',
            )}
            from={event.role === 'assistant' ? 'assistant' : 'user'}
            key={`${event.label}-${event.turn ?? ''}`}
          >
            <MessageContent>
              <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-xs font-medium">
                <span>{event.label}</span>
                {event.marker && (
                  <Badge
                    variant={event.marker === 'P' ? 'destructive' : 'outline'}
                  >
                    {event.marker}
                  </Badge>
                )}
                <Badge variant="secondary">{event.symbol}</Badge>
              </div>
              <MessageResponse className="leading-6 [overflow-wrap:anywhere]">
                {event.body}
              </MessageResponse>
            </MessageContent>
          </Message>
        ))}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  )
}

function OracleTab({ specimen }: { specimen: Specimen }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <PipelineCard
        icon={<LockKeyhole className="size-4" />}
        title="Oracle packet"
      >
        <FormulaBlock latex={evalFormulas.oraclePacket} />
        <div className="grid gap-3">
          <ObjectPanel
            label="u_e"
            title="Trigger instruction"
            text={specimen.triad.instruction}
          />
          <ObjectPanel
            label="a_e"
            title="Logged action on trial"
            text={specimen.triad.action}
          />
          <ObjectPanel
            label="p_e"
            title="Observed pushback"
            text={specimen.triad.pushback}
            tone="danger"
          />
          <ObjectPanel
            label="tail_e"
            title="Logged continuation after pushback"
            text={tailSummary(specimen)}
            tone={
              tailSummary(specimen) ===
              'No downstream continuation is present in this compact artifact.'
                ? 'muted'
                : 'default'
            }
          />
          <ObjectPanel
            label="Δ_e"
            title="Final accepted diff / outcome"
            text="Not present in the current compact artifact."
            tone="muted"
          />
        </div>
      </PipelineCard>

      <aside className="flex flex-col gap-4">
        <PipelineCard
          icon={<ShieldCheck className="size-4" />}
          title="Evaluator-only"
        >
          <p className="text-muted-foreground text-sm leading-6">
            The oracle packet can generate the case rubric, but must never be
            visible to the candidate agent or memory learner for this episode.
          </p>
        </PipelineCard>
        <PipelineCard
          icon={<FileCode2 className="size-4" />}
          title="Workspace evidence"
        >
          {specimen.files.length === 0 ? (
            <p className="text-muted-foreground text-sm leading-6">
              No explicit file paths were found in the compact artifact.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {specimen.files.map((file) => (
                <div
                  className="grid grid-cols-[1rem_minmax(0,1fr)_auto] items-center gap-2 rounded-md bg-muted/45 px-3 py-2 text-sm"
                  key={file.path}
                >
                  <span className="font-mono text-muted-foreground text-xs">
                    {file.status.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="truncate font-mono text-xs">
                    {file.path}
                  </span>
                  <Badge variant="outline">
                    +{file.additions} / -{file.deletions}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </PipelineCard>
      </aside>
    </div>
  )
}

function RubricTab({ specimen }: { specimen: Specimen }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <PipelineCard icon={<Scale className="size-4" />} title="Case rubric">
        <FormulaBlock latex={evalFormulas.rubric} />
        <FormulaBlock latex={evalFormulas.criterion} />
        <EmptyArtifact
          title="Rubric not generated yet"
          body="The current artifact has the oracle packet ingredients, but no persisted list of criteria. Next step is to run G(o_e) and store criteria per episode."
        />
      </PipelineCard>
      <aside className="flex flex-col gap-4">
        <PipelineCard
          icon={<ListChecks className="size-4" />}
          title="Seed judge question"
        >
          <p className="text-muted-foreground text-sm leading-6">
            {specimen.judgeQuestion}
          </p>
        </PipelineCard>
        <PipelineCard
          icon={<CheckCircle2 className="size-4" />}
          title="Positive convention"
        >
          <p className="text-muted-foreground text-sm leading-6">
            A criterion should return 1 when the candidate action satisfies it.
            Avoid inverted flaw-recurs scoring.
          </p>
        </PipelineCard>
      </aside>
    </div>
  )
}

function RunsTab({ specimen }: { specimen: Specimen }) {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PipelineCard icon={<FlaskConical className="size-4" />} title="Cold run">
        <FormulaBlock latex={evalFormulas.coldCandidate} />
        <EmptyArtifact
          title="Cold candidate not run yet"
          body={specimen.coldRisk}
        />
      </PipelineCard>
      <PipelineCard icon={<MemoryStick className="size-4" />} title="Warm run">
        <FormulaBlock latex={evalFormulas.warmCandidate} />
        <EmptyArtifact
          title="Warm candidate not run yet"
          body="Generate k_e, overlay it into w_e, then rerun the same candidate agent/model/config."
        />
      </PipelineCard>
      <section className="xl:col-span-2">
        <PipelineCard
          icon={<FileCode2 className="size-4" />}
          title="Logged trajectory evidence"
        >
          <Terminal output={specimen.trajectory} />
        </PipelineCard>
      </section>
    </div>
  )
}

function ScoresTab({ specimen }: { specimen: Specimen }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <PipelineCard
        icon={<Scale className="size-4" />}
        title="Score definition"
      >
        <FormulaBlock latex={evalFormulas.score} />
        <FormulaBlock latex={evalFormulas.lift} />
        <EmptyArtifact
          title="No scores yet"
          body="Scores require generated rubric criteria plus cold and warm candidate actions."
        />
      </PipelineCard>
      <aside className="flex flex-col gap-4">
        <PipelineCard
          icon={<Table2 className="size-4" />}
          title="Loaded heuristics"
        >
          <KeyValue
            label="Turns from u_e to p_e"
            value={String(specimen.metrics.turnsBeforePushback)}
          />
          <KeyValue
            label="Files mentioned"
            value={String(specimen.metrics.filesTouched)}
          />
          <KeyValue
            label="Trajectory commands"
            value={String(specimen.metrics.toolCalls)}
          />
          <KeyValue
            label="Artifact confidence"
            value={`${Math.round(specimen.metrics.confidence * 100)}%`}
          />
        </PipelineCard>
        <PipelineCard
          icon={<ShieldCheck className="size-4" />}
          title="Preemption"
        >
          <p className="text-muted-foreground text-sm leading-6">
            Count preemption only when cold fails below τ and warm passes at or
            above τ. For the first binary setup, τ = 1.
          </p>
        </PipelineCard>
      </aside>
    </div>
  )
}

function PipelineCard({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-lg border p-4">
      <div className="flex items-center gap-2 font-medium text-sm">
        {icon}
        {title}
      </div>
      {children}
    </section>
  )
}

function ObjectPanel({
  label,
  title,
  text,
  tone = 'default',
}: {
  label: string
  title: string
  text: string
  tone?: 'default' | 'danger' | 'muted'
}) {
  return (
    <section
      className={cn(
        'flex min-w-0 flex-col gap-2 rounded-lg border p-3',
        tone === 'danger' && 'border-destructive/35 bg-destructive/5',
        tone === 'muted' && 'border-dashed bg-muted/25',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={tone === 'danger' ? 'destructive' : 'outline'}>
          {label}
        </Badge>
        <div className="font-medium text-sm">{title}</div>
      </div>
      <MessageResponse className="text-muted-foreground text-sm leading-6 [overflow-wrap:anywhere]">
        {text}
      </MessageResponse>
    </section>
  )
}

function EmptyArtifact({ title, body }: { title: string; body: string }) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-dashed bg-muted/20 p-4">
      <div className="flex items-center gap-2 font-medium text-sm">
        <LockKeyhole className="size-4" />
        {title}
      </div>
      <p className="text-muted-foreground text-sm leading-6">{body}</p>
    </section>
  )
}

function LeakageFirewall() {
  return (
    <section className="grid gap-3 rounded-lg border border-primary/25 bg-primary/5 p-4 md:grid-cols-2 xl:grid-cols-4">
      <FirewallRule
        label="L may see"
        value="d_e only"
        detail="Prior same-repo sessions before s."
      />
      <FirewallRule
        label="A may see"
        value="x_e^0 or x_e^k"
        detail="No pushback, rubric, tail, or answer key."
      />
      <FirewallRule
        label="G may see"
        value="o_e"
        detail="Evaluator-only evidence for rubric generation."
      />
      <FirewallRule
        label="J may see"
        value="R_e and â_e^z"
        detail="Criteria plus candidate action for one arm."
      />
    </section>
  )
}

function FirewallRule({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: string
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="text-primary text-xs font-medium">{label}</div>
      <div className="font-mono text-xs">{value}</div>
      <p className="text-muted-foreground text-xs leading-5">{detail}</p>
    </div>
  )
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="break-all font-mono text-xs">{value}</div>
    </div>
  )
}

function episodeModel(specimen: Specimen): EpisodeModel {
  const instruction = specimen.transcript.find((event) => event.marker === 'I')
  const action = specimen.transcript.find((event) => event.marker === 'A')
  const pushback = specimen.transcript.find((event) => event.marker === 'P')
  const instructionTurn = instruction?.turn ?? Math.max(0, specimen.turn - 2)
  const actionTurn = action?.turn ?? Math.max(0, specimen.turn - 1)
  const pushbackTurn = pushback?.turn ?? specimen.turn
  const historyEvents = specimen.transcript.filter((event) =>
    typeof event.turn === 'number' ? event.turn < instructionTurn : false,
  )
  const tailEvents = specimen.transcript.filter((event) =>
    typeof event.turn === 'number' ? event.turn > pushbackTurn : false,
  )

  return {
    repo: specimen.repo,
    session: specimen.session,
    instructionTurn,
    actionTurn,
    pushbackTurn,
    historyEvents,
    tailEvents,
  }
}

function historySummary(episode: EpisodeModel): string {
  if (episode.historyEvents.length === 0) {
    return 'No earlier prefix turns are present in this compact artifact window. The full rerun should reconstruct h_e from the session transcript before u_e.'
  }

  return episode.historyEvents
    .slice(0, 4)
    .map((event) => `${event.label}: ${event.body}`)
    .join('\n\n')
}

function tailSummary(specimen: Specimen): string {
  const tailEvents = episodeModel(specimen).tailEvents

  if (tailEvents.length === 0) {
    return 'No downstream continuation is present in this compact artifact.'
  }

  return tailEvents
    .slice(0, 4)
    .map((event) => `${event.label}: ${event.body}`)
    .join('\n\n')
}

function countUnits(specimens: Specimen[]): UnitCounts {
  const counts = Object.fromEntries(
    units.map((unit) => [unit.value, 0]),
  ) as UnitCounts

  for (const specimen of specimens) {
    counts[specimen.unit] += 1
  }

  return counts
}

function parseUnit(value: unknown): Unit {
  return units.some((unit) => unit.value === value)
    ? (value as Unit)
    : 'pushbacks'
}

function parsePushback(value: unknown): PushbackSearch {
  return value === 'correction' ||
    value === 'rejection' ||
    value === 'clarification'
    ? value
    : 'all'
}

function parseQuality(value: unknown): QualitySearch {
  return qualityTags.some((tag) => tag === value)
    ? (value as QualityTag)
    : 'all'
}

function parseStarred(value: unknown): StarredSearch {
  return value === 'starred' ? 'starred' : 'all'
}

function parseString(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function parseOptionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

function starStorageKey(source: string, id: string): string {
  return `${source}:${id}`
}

function readStarredCaseKeys(): Set<string> {
  if (typeof window === 'undefined') {
    return new Set()
  }

  try {
    const raw = window.localStorage.getItem(starredStorageKey)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed)
      ? new Set(parsed.filter((item): item is string => typeof item === 'string'))
      : new Set()
  } catch {
    return new Set()
  }
}

function writeStarredCaseKeys(keys: ReadonlySet<string>) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(starredStorageKey, JSON.stringify(Array.from(keys)))
}
