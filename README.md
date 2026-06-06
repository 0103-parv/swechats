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
```

`pushbacks` exports candidate `P` rows only. `eval-cases` is the first-pass
benchmark artifact: it joins each pushback `P` to the preceding assistant action
`A`, the prior user instruction `I`, and same-repo chronological memory-boundary
metadata.

These are still triage artifacts. Human review should drop subjective style-only
cases, unclear corrections, and any case where the reconstructed `I/A/P` window
does not describe the real failure.
