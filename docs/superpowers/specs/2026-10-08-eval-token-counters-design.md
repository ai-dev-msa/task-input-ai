# Eval token counters (2026-10-08)

**Goal:** every eval run reports how many tokens it spent, so prompt/model
changes can be compared before/after (`results.json` totals + a console line
with baseline delta). Dev aid for FR-14; nothing is shown to end users.

## Decisions

- **Source: API usage only.** `llm.complete()` already returns the OpenAI
  `usage` dict in its response — no tiktoken, no new dependency. Offline
  prompt-size estimation is out of scope.
- **Where: eval only.** Totals land in `eval/results.json` under `metrics`
  and in a new Tokens block in the console report. Per-call prints, smoke
  scripts, the `/chat` envelope, and `main.py` stay untouched.
- **Counting point: the runner.** `scripts/run_eval.py` wraps `llm.complete`
  and injects it via the existing `run(complete=...)` seam — production code
  (`llm.py`, `agent.py`) is not modified.

## Data flow

```
run_eval.py
  ├─ usage_rows = []                      (one dict per API call)
  ├─ counting_complete(messages, tools)   ── wraps llm.complete()
  │     response = default_complete(...); usage_rows.append(response.get("usage") or {})
  ├─ run(turn, complete=counting_complete)   ← existing injectable seam
  └─ metrics.update(sum_usage(usage_rows))   ← before print + write
```

- Every API call is counted, so the FR-05 retry (two calls in one turn)
  sums correctly.
- `sum_usage(rows)` is a new pure function in `src/alokasi_agent/eval.py`,
  defensive about missing fields (`prompt_tokens_details` may be absent
  or null; a row may be `{}`).

## results.json shape

Added to the existing `metrics` object (so baseline lookup by key works
unchanged):

```json
"prompt_tokens": 987654,
"completion_tokens": 23456,
"cached_tokens": 876543,
"total_tokens": 1011110,
"llm_calls": 91
```

- `cached_tokens` from `prompt_tokens_details.cached_tokens` (prefix-cache
  hits); 0 when the API omits it.
- `llm_calls = len(usage_rows)` — explains token jumps from retries.
- `--update-baseline` copies the payload wholesale, so tokens ride along.

## Console report

New block after Headline, same baseline-delta style. Delta prints only when
the old baseline contains the key (existing baselines do not, so the first
run after this change shows no delta):

```
Tokens
  prompt tokens         : 987654 (baseline 1000000, delta -12346)
  completion tokens     : 23456
  cached prompt tokens  : 876543
  total tokens          : 1011110 (baseline 1030000, delta -18890)
  llm calls             : 91
```

## Files affected

| File | Change |
|---|---|
| `scripts/run_eval.py` | counting wrapper + `complete=` injection + Tokens report block |
| `src/alokasi_agent/eval.py` | new pure `sum_usage()` |
| `tests/test_eval.py` | unit tests for `sum_usage` |
| `eval/results.json`, `eval/baseline.json` | rewritten by the script (data, not edited by hand) |

Untouched: `src/alokasi_agent/llm.py`, `agent.py`, `prompt.py`, `main.py`.

## Testing

- `tests/test_eval.py`: `sum_usage` with an empty list, several rows summed,
  a `{}` row, missing `prompt_tokens_details`, and `cached_tokens` extraction.
- No runner-wiring test (run_eval has none today — existing pattern).
- Verify: `.venv\Scripts\python.exe -m pytest`, then a live
  `.venv\Scripts\python.exe scripts\run_eval.py --limit 1`
  (needs `OPENAI_API_KEY`, spends a few calls).

## Out of scope

tiktoken/offline counting, per-call console lines, smoke-script totals,
envelope/`main.py` changes, per-case token breakdowns.
