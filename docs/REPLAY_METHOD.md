# Counterfactual Replay Method

## Decision

The primary benchmark must fail closed. A case is scored only when we can
certify the semantic state immediately after instruction `I` and before the
original action `A`. Cases that are merely plausible reconstructions remain
exploratory and are excluded from headline results.

The best replay source is an Entire temporary shadow checkpoint at the target
boundary. It contains a full worktree snapshot plus the native transcript.
Public SWE-chat does not publish those checkpoints, so most public-data cases
require reconstruction and independent validation.

## What Must Be Forked

The semantic fork state is:

1. Repository state: `HEAD`, tracked worktree bytes, index, deletions, untracked
   files, submodules, and LFS objects relevant to the task.
2. Conversation state: exact native transcript prefix through `I`.
3. Runner state: agent/system instructions, tools, permissions, working
   directory, model, and decoding/configuration values.
4. Execution state needed by the task: dependency lockfiles and installed
   versions, fixtures, services, environment variables, and platform details.
5. Intervention: the cold arm receives no learned memory; the warm arm differs
   only by the generated repo memory.

Provider prompt-cache contents are not semantic state. Cache creation/read token
counts affect latency and billing, not the model-visible conversation. Do not
attempt to clone provider cache state; hash and hold the transcript, model, and
configuration constant instead.

## What The Published Methods Support

The SWE-chat paper's post-hoc provenance analysis starts from the parent commit,
replays file-modifying tool calls in order, and compares line states with
`difflib.SequenceMatcher`. The paper explicitly notes that concurrent human and
agent edits can make transcript states and attribution inconsistent. That method
is appropriate for aggregate provenance metrics, but it does not certify the
complete environment at an arbitrary intermediate turn.

Entire itself has the stronger artifact:

- Temporary checkpoint: full state on a local shadow branch, used for rewind.
- Committed checkpoint: permanent metadata plus a commit reference.
- On the first temporary checkpoint, Entire captures changed tracked,
  untracked, renamed, and deleted worktree files.
- Shadow branches are local, unredacted, deliberately not pushed, and deleted
  after condensation.

This means exact intermediate replay is supported by Entire's architecture, but
the required temporary artifact is normally absent from public SWE-chat.

## Fidelity Tiers

| Tier | Evidence | Primary benchmark |
|---|---|---|
| `S` | Exact native temporary snapshot at the fork boundary | Yes |
| `A` | Exact base commit and proof that the fork worktree was clean | Yes |
| `B` | Exact base plus replay, validated against independent state anchors | Yes, with validation recorded |
| `C` | Parent/base plus unvalidated tool replay or inferred state | No; exploratory only |
| `R` | Missing/inconsistent transcript, commit, or replay evidence | Reject |

Tier `B` validation must compare reconstructed file bytes or Git tree hashes
against evidence not used to perform the replay. A successful application of
the same logged edits is not independent validation.

## Public-Data Replay Procedure

1. Resolve `I`, `A`, and correction/rejection `P`.
2. Extract and hash both the native history before `I` and the transcript
   through `I`. Candidate execution resumes the history-only prefix, then
   submits `I` as the new prompt.
3. Identify the exact base commit. Reject if commit mapping is missing or
   ambiguous.
4. Search for a snapshot or clean-worktree proof at the boundary.
5. If the boundary is intermediate, replay every earlier state-changing action.
   Treat arbitrary shell calls and out-of-band human edits as unresolved until
   classified or independently validated.
6. Materialize one certified fork, duplicate it into cold and warm arms, and
   verify identical pre-intervention tree and transcript hashes.
7. Inject memory only into the warm arm. Run both arms with the same runner and
   model configuration.
8. Judge the narrow question: does the candidate still exhibit the flaw
   described by `P`?
9. Record every excluded case and its reason.

## Judging Contract

The judge receives `I`, candidate output/diff, `P`, and the original `A` only as
context. It returns the positive eval convention:

- `1`: the specific flaw described by `P` is avoided.
- `0`: that flaw recurs.
- abstain outside scoring when the candidate lacks enough observable evidence.

Downstream turns or final diffs may clarify intent, but they are not a checklist
the one-turn counterfactual must reproduce.

The prototype bundle stores `original-trajectory.jsonl` from immediately after
`I` to immediately before `P`. This is calibration context for locating the
original flaw when it occurred in an edit or tool call rather than the final
assistant prose. A rerun must likewise preserve its assistant response,
repository diff, and tool trajectory for the judge.

## First Real Case

For session `0158ecff-f487-4f8a-91cb-2352d929ee0c`, pushback turn `24`:

- The native transcript prefix through the initial changelog request is exact.
- The session's commit mappings are available.
- A post-instruction read-only Git command strongly indicates the original
  `HEAD` was `bc0448c6c67cb8c5e90c46811487d1e2ad8a36fa`.
- Public artifacts do not prove the original worktree was clean.

Therefore this is a useful reconstructed smoke-test candidate, but it is not yet
eligible for the primary benchmark. The harness should say that plainly rather
than silently upgrading it to an exact fork.

## Harness Rule

Every run must carry a replay manifest. A run without a recorded tier,
history-prefix hash, repository-state hash, runner configuration, and
exclusion/validation evidence is not a benchmark result.

## Current Prototype

Create an immutable case bundle:

```bash
uv run swechats case-bundle \
  0158ecff-f487-4f8a-91cb-2352d929ee0c 24 \
  data/replay-smoke/changelog-turn-24
```

Audit another case without stopping on missing evidence:

```bash
uv run swechats replay-audit <session-id> <pushback-turn-number>
```

Materialize paired forks. Non-primary cases are refused unless the caller
explicitly labels the run exploratory:

```bash
uv run swechats fork-pair \
  data/replay-smoke/changelog-turn-24 \
  data/repos/entireio-cli.git \
  bc0448c6c67cb8c5e90c46811487d1e2ad8a36fa \
  --allow-exploratory
```

The fork manifest records the resolved commit, independent Git state,
observed-action replay ledger, path-rebased native history, cold/warm
pre-intervention hashes, post-intervention hashes, and memory injection.

## Narrowed Experiment Prerequisites

For the reconstructed-context experiment, the workspace claim is intentionally:

```text
reconstructed workspace
  = declared base commit
  + every observed agent workspace mutation before the trigger instruction
```

Unknown human edits are not reconstructed and are explicitly outside the
claim. This is sufficient only if every observed pre-boundary agent tool call is
classified. Read-only/non-workspace calls may be skipped for workspace
construction; every mutating call must replay successfully with strict
preconditions; any unsupported, ambiguous, or potentially mutating unknown call
rejects the episode.

The two load-bearing gates are:

### Gate H: Native History Re-entry

- The native Claude history prefix ends immediately before `u_e`.
- Candidate execution resumes that history and submits `u_e` as the new prompt.
- The history contains no trigger instruction, original candidate action,
  pushback, or future turns.
- Historical workspace paths are mapped consistently into the isolated arm.
- `claude --resume <session> --fork-session` successfully consumes the prefix.
- A read-only canary demonstrates access to both prior history and current
  reconstructed workspace state.
- The canary leaves the workspace and Git state unchanged.

### Gate W: Observed-Agent Workspace Reconstruction

- Each arm is an independent Git repository, not an archive nested under
  another repository.
- Both arms resolve to the declared base commit and equivalent Git state.
- The replay ledger covers every observed agent tool call before `u_e`.
- Every observed mutation is replayed in chronological order.
- Edit operations require their exact old content to exist unambiguously.
- Bash calls must be proven read-only or the episode is rejected.
- Cold and warm replay ledgers and resulting workspace hashes match before
  memory injection.

Only after both gates pass for an episode may it enter a scored run. Passing
these gates supports the claim:

> Memory changes candidate behavior in a controlled reconstruction consisting
> of the declared base plus all observable prior agent mutations.

It does not support the stronger claim that the reconstruction equals the
historical human worktree.

### Verified Smoke Evidence

For the changelog session's correction at turn `41`:

- Base commit: `bc0448c6c67cb8c5e90c46811487d1e2ad8a36fa`
- Four observed pre-boundary tool calls were classified.
- Three Bash calls were proven read-only.
- One `Edit` to `CHANGELOG.md` replayed with matching before/after hashes.
- Cold and warm reconstructed workspace hashes matched.
- Cold and warm were independent Git repositories with matching `HEAD`, index,
  refs, tags, and status.
- The native transcript was path-rebased into the cold arm.
- Claude Code resumed it with `--fork-session` and correctly returned both the
  exact prior user instruction and a fact read from the replayed changelog.
- The read-only canary left the workspace hash unchanged.

This demonstrates feasibility on one episode. The harness still needs an
automated per-episode re-entry canary before scored batch experiments begin.
