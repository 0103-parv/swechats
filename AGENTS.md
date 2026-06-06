# SWE-chat Memory Hackathon Repo

This repo is a hackathon workspace for exploring repo-bound agent memory using
the SWE-chat dataset. Prefer practical, verifiable progress over big framework
design. Keep claims scoped to what the current code/data actually supports.

## Project Idea

Build an eval-first prototype for learning repository-local agent memory from
past coding-agent conversations.

The core hypothesis:

> If an agent has useful repo-local memory, it should avoid some of the same
> mistakes that caused real users in SWE-chat to correct or reject prior agent
> outputs.

The important framing is not "summarize chats into memory." The sharper problem
is deciding what should become durable memory, where it belongs, and whether it
prevents real correction-worthy failures.

## Current Repo State

- `docs/swe-chat-paper.md` is the local text of the SWE-chat paper.
- `docs/HACKATHON_CTX.md` contains hackathon logistics, judging criteria, and
  sponsor/tooling context.
- `vendor/SWE-chat/` contains the official `SALT-NLP/SWE-chat` GitHub repo.
  As of vendoring, upstream only has README/LICENSE and says data/code are
  coming soon.
- `data/` is ignored by git/jj and is for local Hugging Face downloads.
- `src/swechats/` contains a lightweight Python CLI for local data inspection,
  candidate pushback export, and first-pass `I/A/P` eval-case extraction.

## Data Sources

Official public sources:

- Website: `https://www.swe-chat.com/`
- GitHub: `https://github.com/SALT-NLP/SWE-chat`
- Hugging Face dataset: `https://huggingface.co/datasets/SALT-NLP/SWE-chat`
- Paper: `https://arxiv.org/abs/2604.20779`

Use local files first when available. The Hugging Face dataset should live under
`data/swe-chat/` and remain untracked.

Expected HF dataset shape includes:

- `sessions.parquet`
- `session_logs.parquet`
- `repositories.parquet`
- `checkpoints.parquet`
- `conversations.parquet`
- `commits.parquet`
- `transcripts/*.jsonl`

The large files are normal. Do not add `data/` to version control.

## Evaluation Direction

The likely hackathon MVP is a counterfactual correction-prevention eval:

1. Select SWE-chat turns where the user pushback label is `correction` or
   `rejection`.
2. For each eval case identify:
   - `I`: the user instruction before the problematic agent action.
   - `A`: the original agent response/diff/action that drew pushback.
   - `P`: the next user pushback explaining what was wrong.
   - Optional downstream turns/final committed diff as intent context for the
     judge.
3. Build memory from earlier sessions in the same repo, never from the held-out
   eval session.
4. Compare two arms with the same model:
   - cold: no learned repo memory
   - warm: generated repo memory injected as repo state, such as `AGENTS.md`
5. Judge whether the new agent output still exhibits the flaw described by `P`.

Keep the claim narrow:

> We measure whether learned repo memory preempts specific corrections users
> actually made.

Do not overclaim that the method proves users would be fully satisfied or that
the final repo state would match the original downstream conversation.

## Memory Product Shape

Generated memory should target repo-native agent affordances:

- `AGENTS.md` for declarative repo conventions, gotchas, and preferences.
- `SKILL.md` files for procedural repeatable workflows.
- Hierarchical placement when useful: root repo memory for broad facts, nested
  memory for package/path-specific rules.

Important distinction:

- A one-off incident should usually not become durable memory.
- A repeated convention, repo invariant, setup rule, or correction pattern is a
  stronger memory candidate.

## Multi-Agent Harness

The intended sponsor-friendly architecture can be small:

- Proposer: reads prior sessions and proposes candidate memories.
- Critic: rejects one-off noise, leakage, vague advice, and redundant memories.
- Placer: chooses root `AGENTS.md`, nested `AGENTS.md`, or `SKILL.md`.
- Evaluator/Judge: scores cold vs warm outputs against real pushback text.

Trace these steps in W&B Weave when implementing. The Weave trace is part of the
demo, not a decorative add-on.

## Methodology Guardrails

- Avoid leakage. For session `t`, memory must come only from sessions before
  `t` in the same repo or chosen memory domain.
- Prefer chronological splits over random splits because that matches deployed
  memory accumulation.
- Run cold and warm with the same model/config.
- Treat LLM annotations in SWE-chat as filter aids, not ground truth.
- Prefer binary flaw recurrence judgments over broad "quality" scores.
- Use downstream messages/final diffs as judge context for intent, not as a
  literal checklist for a one-turn counterfactual.
- Track dropped cases and why: missing data, unclear pushback, impossible repo
  reconstruction, subjective style-only correction, etc.

## Hackathon Judging Angle

Pitch this as an eval/harness project:

- Utility: reduces human correction cycles in real coding-agent workflows.
- Creativity: focuses on memory placement and correction prevention, not generic
  chat summarization.
- Harness sophistication: small team of specialized agents with measurable
  cold-vs-warm outcomes.
- Technical execution: reproducible local data pipeline and concrete examples.
- Sponsor usage: Weave traces, tables, and comparison views for the eval runs.

Demo target:

1. Show one real SWE-chat correction.
2. Show memory learned from earlier sessions only.
3. Show cold output repeating or risking the flaw.
4. Show warm output avoiding it.
5. Show Weave table/trace summarizing several cases.

## Working Practices

- Prefer `jj` over `git` for version-control inspection and workflow.
- Use `rg`/`rg --files` for searching.
- For Python, prefer `uv run python`.
- For one-off Python dependencies, prefer
  `uv run --with <package> python ...`.
- Do not print secrets. If a local `.env` appears later, use it only when the
  user explicitly authorizes credentials for the task.
- Keep generated docs short, direct, and honest about what is live versus planned.
- When adding code, start with a tiny path that can run on a few cases locally.

## Near-Term Implementation Path

Good next steps:

1. Inspect downloaded parquet schemas.
2. Find repos with enough chronological sessions and correction/rejection turns.
3. Produce a small eval-case JSONL with `I`, `A`, `P`, metadata, and leakage
   boundaries.
4. Build a baseline memory generator that writes one root `AGENTS.md`.
5. Add a judge prompt and Weave instrumentation.
6. Only then add hierarchy, skills, or a UI.

Avoid spending early time on full repo replay unless the eval cases require it.
For a first smoke test, curated cases plus source-grounded memory and binary
judging are enough to prove whether the idea has signal.
