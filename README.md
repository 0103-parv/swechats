# swechats

Hackathon workspace for testing whether repo-local agent memory can prevent
real SWE-chat correction/rejection failures.

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
