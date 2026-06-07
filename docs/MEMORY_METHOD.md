# Repo-Memory Learning Method (the `L` side)

## Where this sits

`dspysigs.py` owns the **eval** side: `G` (rubric), `J` (judge), `score_episode`.
It consumes a memory artifact already written into the warm workspace
(`w_e ⊕ k_e`) and asks whether the regenerated action preempts the real
correction. This document + `memory_sigs.py` own the **other** half — producing
that artifact:

```text
L : Sessions -> Memory        k_e := L(d_e)
```

Learn a repo-local memory from prior sessions; render it as repo-native
`AGENTS.md` / nested `AGENTS.md` / `SKILL.md`; the warm arm reads it natively.
The output plugs straight into the existing `fork-pair --memory` injection.

`dspysigs.py:39-41` deliberately punts one firewall to "where `L` lives." This is
where it lives. We enforce it.

## The firewall: the training-signal constraint

Atlas (arXiv 2603.15666): *"the read-path output is bounded by the write-path
input."* The learned memory may contain only what prior sessions taught. One
mechanism, two guarantees:

1. **No-future leak.** `d_e` excludes the held-out session `s` being scored —
   learn from `s' < s` only. The `MemoryCorpus` type physically carries no turn
   from `s` (validated in code).
2. **No fabrication / no bloat.** Every card must share **≥ 2 significant
   keywords with a source prior-session turn** (grounding gate). This kills
   hallucinated repo facts *and* the generic "unnecessary requirements" that the
   AGENTS.md negative result (arXiv 2602.11988) punished.

This single constraint is simultaneously our contamination control and our
defense against the published "context files hurt" result.

## The unit: a decision card

A learned memory is a set of **decision cards**. The card is *correction-shaped*
— it carries exactly the fields a real pushback complains about:

| field | meaning | source |
|---|---|---|
| `when` | trigger condition / recurring situation | clustered prior episodes |
| `do` | canonical action or pattern to copy | prior success / committed outcome |
| `preserve` | invariant that must hold | Atlas **boundary rule** (the correction) |
| `avoid` | anti-pattern / legacy bait not to copy | Atlas **boundary rule** |
| `verify` | cheap proof — content only, the eval never executes it | prior verification turns |

Plus placement (`target_path`, `role`, `altitude_justification`) and provenance
(`evidence[]`, `corroboration_count`, `source_kind`, `confidence`).

**Atlas dual-source:** a prior **correction** → a boundary rule (`preserve`/
`avoid`); a prior **clean committed** turn → a **guard fact** that stops the
critic from deleting a real rule.

## The pipeline

```text
d_e (MemoryCorpus)
  -> Proposer   dspy.RLM explores the corpus -> recurring durable candidate cards
  -> Critic     3-step gate (Atlas): dedup(cosine > 0.92)
                  -> LLM verify {accept|reject|merge|needs_review}, never silent
                  -> grounding (>= 2 keywords); ExpeL importance/corroboration count
  -> Placer     altitude = LCA of evidence file_paths; promote if it generalizes
                  across siblings  (OUR differentiator — ExpeL/AWM/Atlas are flat)
  -> Renderer   cards -> { target_path: markdown }  (root / nested AGENTS.md / SKILL.md)
  = k_e (MemoryArtifact)
```

## One interface, four learners (the ladder)

`MemoryLearner` Protocol: `async learn(corpus) -> MemoryArtifact`. Every baseline
and Ours implement it, so the eval harness in `dspysigs.py` is **identical**
across the ladder:

- **Mem0Learner** — generic retrieval blob (foil).
- **ExpeLLearner** — flat insight list (ADD/EDIT/UPVOTE/DOWNVOTE + importance
  count) → root `AGENTS.md`.
- **AWMLearner** — flat induced workflows, example-specific values abstracted to
  `{placeholders}` → `SKILL.md`.
- **OursLearner** — Proposer → Critic → Placer → Render.

Ladder: `cold < Mem0 < ExpeL/AWM < Ours`. The lift from ExpeL→Ours is
attributable to the **critic gate + placement** — the two things the baselines
don't have.

## Deliberately NOT done

- **No full 8-role hierarchy / every-section files.** That is the +20%-cost bloat
  the negative result punished. Emit only delta cards that real corrections
  evidence.
- **No maintenance frontmatter** (`owners`, `last_reviewed`, lint rules). That is
  for human authors; our freshness = re-run `L` at each chronological cutoff.
- **`verify` is content only.** The read-only eval recommends it, never runs it.
- **v1 clamps all cards to root `AGENTS.md`** (single file, plugs into the
  current `fork-pair --memory`). Nested placement is the v2 "metric climbs as we
  add levels" upgrade (placer unclamp + multi-file warm injection).

## Reproduction map (baselines → our parts)

- **ExpeL** (2308.10144): the insight loop = our Proposer + Critic count, run over
  `d_e`; fail/success pairs = prior correction episodes (leakage-safe).
- **AWM** (2409.07429): workflow induction + value abstraction → `SKILL.md`;
  offline scenario = our chronological holdout.
- **Atlas** (2603.15666): the 3-step gate, dual-source extraction, and the
  training-signal constraint.

**Ours = Atlas verified-compile + AWM abstraction + the altitude placer +
repo-local holdout, judged on real human corrections (+ cost).**
