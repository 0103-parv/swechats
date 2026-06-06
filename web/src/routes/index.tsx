import {
  Conversation,
  ConversationContent,
} from '#/components/ai-elements/conversation'
import { Message, MessageContent } from '#/components/ai-elements/message'
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
import { Checkbox } from '#/components/ui/checkbox'
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
import { Separator } from '#/components/ui/separator'
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
  PushbackKind,
  QualityTag,
  Specimen,
  Unit,
} from '#/lib/swechat/specimens'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import {
  CheckCircle2,
  Database,
  FileCode2,
  Filter,
  GitBranch,
  ListChecks,
  Search,
  Sparkles,
  Table2,
} from 'lucide-react'

type PushbackSearch = PushbackKind | 'all'
type QualitySearch = QualityTag | 'all'

type SearchState = {
  unit: Unit
  repo: string
  pushback: PushbackSearch
  quality: QualitySearch
  q: string
  selected: string | undefined
}

export const Route = createFileRoute('/')({
  validateSearch: (search): SearchState => ({
    unit: parseUnit(search.unit),
    repo: parseString(search.repo, 'all'),
    pushback: parsePushback(search.pushback),
    quality: parseQuality(search.quality),
    q: parseString(search.q, ''),
    selected: parseOptionalString(search.selected),
  }),
  loader: () => loadSpecimens(),
  component: Home,
})

function Home() {
  const { specimens, source } = Route.useLoaderData()
  const search = Route.useSearch()
  const navigate = useNavigate({ from: '/' })
  const repos = Array.from(new Set(specimens.map((item) => item.repo))).sort()
  const filtered = filterSpecimens(specimens, search)
  const selected =
    filtered.find((item) => item.id === search.selected) ||
    filtered[0] ||
    specimens[0]

  const patchSearch = (patch: Partial<SearchState>) =>
    navigate({
      search: (current) => ({
        ...current,
        ...patch,
        selected: patch.selected ?? current.selected,
      }),
    })

  return (
    <main className="flex h-dvh min-h-[720px] flex-col bg-background text-foreground">
      <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg border bg-muted">
            <Database className="size-4" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate font-heading text-lg font-medium">
              SWE-chat specimen viewer
            </h1>
            <p className="truncate text-muted-foreground text-xs">
              {source.loaded} cases from {source.path}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="secondary">{source.kind}</Badge>
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
          unit={search.unit}
          onChange={patchSearch}
        />
        <CandidateList
          cases={filtered}
          selectedId={selected?.id}
          onSelect={(id) => patchSearch({ selected: id })}
        />
        <DetailPane specimen={selected} />
      </div>
    </main>
  )
}

function FilterRail({
  unit,
  repo,
  repos,
  pushback,
  quality,
  query,
  onChange,
}: {
  unit: Unit
  repo: string
  repos: string[]
  pushback: PushbackSearch
  quality: QualitySearch
  query: string
  onChange: (patch: Partial<SearchState>) => void
}) {
  return (
    <aside className="flex min-h-0 flex-col gap-5 border-r bg-muted/25 p-4">
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
            <ToggleGroupItem key={item.value} value={item.value}>
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
            <SelectItem key={item} value={item}>
              {item}
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
          <Sparkles className="size-4" />
          Eval claim
        </div>
        <p className="text-muted-foreground text-xs leading-5">
          The loader favors held-out I/A/P artifacts. Downstream transcript text
          is context for judging intent, not a checklist for one generated turn.
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

function CandidateList({
  cases,
  selectedId,
  onSelect,
}: {
  cases: Specimen[]
  selectedId: string | undefined
  onSelect: (id: string) => void
}) {
  return (
    <section className="flex min-h-0 flex-col border-r">
      <div className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <div className="font-medium text-sm">Candidates</div>
        <Badge variant="outline">{cases.length}</Badge>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-3 p-3">
          {cases.map((item) => (
            <button
              className="text-left"
              key={item.id}
              type="button"
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
                  <CardTitle className="line-clamp-2 text-sm">
                    {item.title}
                  </CardTitle>
                  <CardDescription className="flex items-center gap-2 text-xs">
                    <GitBranch className="size-3" />
                    {item.repo} / turn {item.turn}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3 px-3">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="secondary">{item.pushback}</Badge>
                    <Badge variant="outline">{item.intent}</Badge>
                    {item.cleanAttribution && (
                      <Badge variant="outline">clean attribution</Badge>
                    )}
                  </div>
                  <p className="line-clamp-3 text-muted-foreground text-xs leading-5">
                    {item.triad.pushback}
                  </p>
                </CardContent>
              </Card>
            </button>
          ))}
        </div>
      </ScrollArea>
    </section>
  )
}

function DetailPane({ specimen }: { specimen: Specimen | undefined }) {
  if (!specimen) {
    return (
      <section className="grid min-h-0 place-items-center text-muted-foreground text-sm">
        No candidate selected.
      </section>
    )
  }

  return (
    <section className="flex min-h-0 flex-col">
      <div className="flex h-16 shrink-0 items-center justify-between gap-3 border-b px-5">
        <div className="min-w-0">
          <h2 className="truncate font-heading text-base font-medium">
            {specimen.title}
          </h2>
          <p className="truncate text-muted-foreground text-xs">
            {specimen.session} / {specimen.agent} / {specimen.codingMode}
          </p>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button size="sm" variant="outline">
              <ListChecks data-icon="inline-start" />
              Score case
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Judge cold vs warm against the held-out pushback flaw.
          </TooltipContent>
        </Tooltip>
      </div>

      <Tabs className="flex min-h-0 flex-1 flex-col" defaultValue="triad">
        <div className="border-b px-5 py-2">
          <TabsList>
            <TabsTrigger value="triad">Triad</TabsTrigger>
            <TabsTrigger value="transcript">Transcript</TabsTrigger>
            <TabsTrigger value="trajectory">Trajectory</TabsTrigger>
            <TabsTrigger value="provenance">Provenance</TabsTrigger>
            <TabsTrigger value="metrics">Metrics</TabsTrigger>
            <TabsTrigger value="raw">Raw</TabsTrigger>
          </TabsList>
        </div>

        <ScrollArea className="min-h-0 flex-1">
          <TabsContent className="m-0 p-5" value="triad">
            <Triad specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="transcript">
            <Transcript specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="trajectory">
            <Trajectory specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="provenance">
            <Provenance specimen={specimen} />
          </TabsContent>
          <TabsContent className="m-0 p-5" value="metrics">
            <Metrics specimen={specimen} />
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

function Triad({ specimen }: { specimen: Specimen }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex flex-col gap-4">
        <TriadBlock label="I - instruction" text={specimen.triad.instruction} />
        <TriadBlock label="A - action on trial" text={specimen.triad.action} />
        <TriadBlock
          label="P - held-out pushback"
          text={specimen.triad.pushback}
        />
      </div>
      <aside className="flex flex-col gap-4">
        <section className="flex flex-col gap-3 rounded-lg border p-4">
          <div className="font-medium text-sm">Candidate checklist</div>
          {qualityTags.map((tag) => (
            <label
              className="grid grid-cols-[1rem_minmax(0,1fr)] items-start gap-3 text-sm leading-5"
              key={tag}
            >
              <Checkbox
                checked={specimen.quality.includes(tag)}
                className="mt-0.5"
                disabled
              />
              <span className="min-w-0 break-words">{tag}</span>
            </label>
          ))}
        </section>
        <section className="flex flex-col gap-2 rounded-lg border p-4">
          <div className="font-medium text-sm">Why memory might help</div>
          <p className="text-muted-foreground text-sm leading-6">
            {specimen.memoryHypothesis}
          </p>
        </section>
        <section className="flex flex-col gap-2 rounded-lg border p-4">
          <div className="font-medium text-sm">Judge question</div>
          <p className="text-muted-foreground text-sm leading-6">
            {specimen.judgeQuestion}
          </p>
        </section>
      </aside>
    </div>
  )
}

function TriadBlock({ label, text }: { label: string; text: string }) {
  return (
    <section className="flex min-w-0 flex-col gap-2 rounded-lg border p-4">
      <div className="text-muted-foreground text-xs font-medium uppercase">
        {label}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-6 [overflow-wrap:anywhere]">
        {text}
      </p>
    </section>
  )
}

function Transcript({ specimen }: { specimen: Specimen }) {
  return (
    <Conversation className="h-[620px] rounded-lg border">
      <ConversationContent className="gap-4">
        {specimen.transcript.map((event) => (
          <div
            className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3"
            key={event.label}
          >
            <div className="flex size-8 items-center justify-center rounded-md border bg-muted font-mono text-xs">
              {event.symbol}
            </div>
            <Message from={event.role === 'assistant' ? 'assistant' : 'user'}>
              <MessageContent>
                <div className="text-muted-foreground text-xs font-medium">
                  {event.label}
                </div>
                <p className="whitespace-pre-wrap leading-6 [overflow-wrap:anywhere]">
                  {event.body}
                </p>
              </MessageContent>
            </Message>
          </div>
        ))}
      </ConversationContent>
    </Conversation>
  )
}

function Trajectory({ specimen }: { specimen: Specimen }) {
  return (
    <div className="flex flex-col gap-5">
      <Terminal output={specimen.trajectory} />
      <div className="grid gap-3 md:grid-cols-2">
        <section className="flex flex-col gap-2 rounded-lg border p-4">
          <div className="font-medium text-sm">Cold risk</div>
          <p className="text-muted-foreground text-sm leading-6">
            {specimen.coldRisk}
          </p>
        </section>
        <section className="flex flex-col gap-2 rounded-lg border p-4">
          <div className="font-medium text-sm">Warm memory candidate</div>
          <p className="text-muted-foreground text-sm leading-6">
            {specimen.warmMemory}
          </p>
        </section>
      </div>
    </div>
  )
}

function Provenance({ specimen }: { specimen: Specimen }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="flex flex-col gap-3 rounded-lg border p-4">
        <div className="flex items-center gap-2 font-medium text-sm">
          <FileCode2 className="size-4" />
          Files
        </div>
        {specimen.files.length === 0 ? (
          <p className="text-muted-foreground text-sm">
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
                <span className="truncate font-mono text-xs">{file.path}</span>
                <Badge variant="outline">
                  +{file.additions} / -{file.deletions}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="flex flex-col gap-3 rounded-lg border p-4">
        <div className="font-medium text-sm">Boundary</div>
        <KeyValue label="Base" value={specimen.provenance.baseCommit} />
        <KeyValue label="Checkpoint" value={specimen.provenance.checkpoint} />
        <KeyValue label="Attribution" value={specimen.provenance.attribution} />
        <Separator />
        <p className="text-muted-foreground text-sm leading-6">
          {specimen.provenance.leakageBoundary}
        </p>
      </section>
    </div>
  )
}

function Metrics({ specimen }: { specimen: Specimen }) {
  const metrics = [
    ['Turns to P', specimen.metrics.turnsBeforePushback.toString()],
    ['Files touched', specimen.metrics.filesTouched.toString()],
    ['Tool calls', specimen.metrics.toolCalls.toString()],
    ['Confidence', `${Math.round(specimen.metrics.confidence * 100)}%`],
  ]

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {metrics.map(([label, value]) => (
        <Card className="rounded-lg" key={label} size="sm">
          <CardHeader>
            <CardDescription>{label}</CardDescription>
            <CardTitle className="text-2xl">{value}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-muted-foreground text-xs">
              <CheckCircle2 className="size-3.5" />
              Loaded from specimen artifact
            </div>
          </CardContent>
        </Card>
      ))}
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

function filterSpecimens(specimens: Specimen[], search: SearchState) {
  const query = search.q.trim().toLowerCase()

  return specimens.filter((item) => {
    if (search.repo !== 'all' && item.repo !== search.repo) {
      return false
    }
    if (search.pushback !== 'all' && item.pushback !== search.pushback) {
      return false
    }
    if (search.quality !== 'all' && !item.quality.includes(search.quality)) {
      return false
    }
    if (!query) {
      return true
    }

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
      .includes(query)
  })
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

function parseString(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function parseOptionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}
