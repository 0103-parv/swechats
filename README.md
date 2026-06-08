# swechats

**Do AI coding agents repeat the mistakes their users already corrected — and can repo-local memory stop them?**

Benchmarks say coding agents keep getting smarter; real sessions tell a different story — they repeat the exact mistake a developer corrected minutes earlier. **swechats** learns repo-specific memory from real human–agent coding sessions, writes it back as the agent's own native `AGENTS.md`, then **rewinds each session to the moment a user pushed back** and measures whether that memory would have prevented the correction.

Built on Stanford's in-the-wild [SWE-chat](https://huggingface.co/datasets/SALT-NLP/SWE-chat) dataset. Co-built with [@darinkishore](https://github.com/darinkishore).

> Active research build — we measure *whether* learned memory preempts real corrections; we don't claim it does (yet).

## The idea

A coding agent fails in a way standard benchmarks never see: it repeats a mistake its user already corrected one session ago. swechats turns that signal into memory.

1. **Mine** prior same-repo sessions for the lessons behind real corrections.
2. **Distill** them into decision cards — `when / do / preserve / avoid / verify` — under a strict leakage firewall: learn only from sessions *before* the one being tested, so the memory never sees the answer.
3. **Inject** them as native `AGENTS.md` the agent reads on its own — the real mechanism, not a proxy.
4. **Replay** the exact turn a user corrected the agent, cold (no memory) vs warm (with memory), and judge whether the warm run preempts the correction.

The whole point is the counterfactual: same agent, same model, same instruction — the only difference is the repo's learned memory.

## Repo tour

| Path | What it is |
|---|---|
| `src/swechats/memory_sigs.py` | the memory learner `L` — Proposer → Critic → Placer → render |
| `src/swechats/dspysigs.py` | the counterfactual eval — rubric generator `G` + judge `J` |
| `src/swechats/replay.py` | replay harness — paired cold/warm forks, native Claude re-entry |
| `src/swechats/cases.py`, `candidate_filter.py` | episode extraction + LLM triage of real corrections |
| `docs/MEMORY_METHOD.md` · `docs/REPLAY_METHOD.md` · `docs/system_def.md` | method, replay rigor, formal spec |

## Local Data

The official SWE-chat code repo is vendored at `vendor/SWE-chat/`, but upstream
currently contains only README/LICENSE. The usable dataset comes from Hugging
Face and is intentionally ignored under `data/`.

```bash
hf download SALT-NLP/SWE-chat --repo-type dataset --local-dir data/swe-chat
```

## Useful Commands

```bash
uv run swechats overview
uv run swechats schema conversations
uv run swechats repo-counts --limit 10
uv run swechats pushback-counts
uv run swechats pushbacks --repo entireio/cli --limit 20
uv run swechats eval-cases artifacts/eval-cases-entireio-cli.jsonl --repo entireio/cli --limit 20
WANDB_API_KEY=... uv run swechats filter-candidates \
  artifacts/eval-cases-entireio-cli.jsonl \
  artifacts/filtered-eval-cases-entireio-cli.jsonl \
  --weave-project entity/project
uv run swechats replay-smoke artifacts/replay-smoke-real --memory-learner ours
uv run swechats replay-smoke artifacts/replay-smoke-local \
  --memory-learner placeholder --skip-claude --skip-dspy
```

`pushbacks` exports candidate `P` rows only. `eval-cases` is the first-pass
benchmark artifact: it joins each pushback `P` to the preceding assistant action
`A`, the prior user instruction `I`, and same-repo chronological memory-boundary
metadata.

These are still triage artifacts. Human review should drop subjective style-only
cases, unclear corrections, and any case where the reconstructed `I/A/P` window
does not describe the real failure.

`filter-candidates` runs W&B Inference through its OpenAI-compatible API and
traces each candidate verdict with Weave. The Weave project resolves from
`--weave-project`, then `WEAVE_PROJECT`, then `WANDB_PROJECT`, then `swechats`.
The default model is W&B's Kimi K2.6 API id, `moonshotai/Kimi-K2.6`;
temperature is `1.0`, and no `max_tokens` limit is sent unless `--max-tokens`
is explicitly set.

The committed filter artifact is
`data/kimi-filter-output-entireio-cli-temp1-full.jsonl`: 2,095 `entireio/cli`
I/A/P candidates scored with Kimi K2.6 at temperature `1.0` and no client
`max_tokens` cap. It contains 118 `keep`, 32 `needs_review`, and 1,945 `drop`
decisions.

`replay-smoke` defaults to the real `ours` memory learner. It builds a typed
chronological corpus from correction/rejection episodes in prior same-repo
sessions, runs Proposer → Critic → Placer, records the structured artifact, and
injects its rendered markdown only into the warm arm.

## License

MIT — see [LICENSE](LICENSE). Co-built by Parv Mehndiratta and Darin Kishore.
