# Eval Token Counters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every eval run reports total tokens spent (results.json + console block with baseline delta) so prompt/model changes can be compared.

**Architecture:** The eval runner wraps `llm.complete()` with a counting closure and injects it through the existing `run(complete=...)` seam; a new pure `sum_usage()` in `eval.py` totals the recorded usage dicts, which the runner merges into `metrics` for the report and `eval/results.json`. Production code (`llm.py`, `agent.py`, `prompt.py`, `main.py`) is untouched.

**Tech Stack:** Python 3.11+, stdlib only (no new dependencies — usage comes from the OpenAI response), pytest.

## Global Constraints

- No new dependencies (tiktoken explicitly out of scope; source is the API response `usage` dict).
- Tests: `.venv\Scripts\python.exe -m pytest` (from repo root, Windows).
- No git commits unless the user explicitly asks (AGENTS.md).
- Do not modify `src/alokasi_agent/llm.py`, `agent.py`, `prompt.py`, or `main.py`.
- Spec: `docs/superpowers/specs/2026-10-08-eval-token-counters-design.md`.

---

### Task 1: `sum_usage()` in `eval.py`

**Files:**
- Modify: `src/alokasi_agent/eval.py` (append after `aggregate()`, end of file)
- Test: `tests/test_eval.py`

**Interfaces:**
- Consumes: nothing (pure function; `Any` is already imported in `eval.py`).
- Produces: `sum_usage(usage_rows: list[dict[str, Any]]) -> dict[str, int]` returning keys `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens` — Task 2 calls this and merges the result into `metrics`.

- [ ] **Step 1: Add `sum_usage` to the test file import**

In `tests/test_eval.py`, extend the existing import block (lines 6-13) to include `sum_usage`:

```python
from alokasi_agent.eval import (
    aggregate,
    classify,
    load_cases,
    load_fixture,
    parse_summary,
    score_turn,
    sum_usage,
)
```

- [ ] **Step 2: Write the failing tests**

Append to the end of `tests/test_eval.py`:

```python
# --- sum_usage ---


def test_sum_usage_empty_rows():
    assert sum_usage([]) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
    }


def test_sum_usage_sums_every_call():
    rows = [
        {
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "prompt_tokens_details": {"cached_tokens": 80},
        },
        {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
    ]
    assert sum_usage(rows) == {
        "prompt_tokens": 150,
        "completion_tokens": 15,
        "total_tokens": 165,
        "cached_tokens": 80,
    }


def test_sum_usage_tolerates_missing_usage_fields():
    rows = [
        {},
        {
            "prompt_tokens": 7,
            "completion_tokens": 1,
            "total_tokens": 8,
            "prompt_tokens_details": None,
        },
    ]
    assert sum_usage(rows) == {
        "prompt_tokens": 7,
        "completion_tokens": 1,
        "total_tokens": 8,
        "cached_tokens": 0,
    }
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -v`
Expected: FAIL — `ImportError: cannot import name 'sum_usage' from 'alokasi_agent.eval'`.

- [ ] **Step 4: Write the implementation**

Append to the end of `src/alokasi_agent/eval.py` (after `aggregate()`):

```python
def sum_usage(usage_rows: list[dict[str, Any]]) -> dict[str, int]:
    """Totals over the usage dict of every API call in a run.

    A row may be {} when the API omitted usage entirely, and
    prompt_tokens_details may be absent or null.
    """
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
    }
    for row in usage_rows:
        totals["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(row.get("completion_tokens") or 0)
        totals["total_tokens"] += int(row.get("total_tokens") or 0)
        details = row.get("prompt_tokens_details") or {}
        totals["cached_tokens"] += int(details.get("cached_tokens") or 0)
    return totals
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -v`
Expected: PASS — the three new `test_sum_usage_*` tests pass.

---

### Task 2: Counting wrapper + Tokens report in `run_eval.py`

**Files:**
- Modify: `scripts/run_eval.py`

**Interfaces:**
- Consumes: `sum_usage()` from Task 1; `run(..., complete=...)` (existing seam in `agent.py`); `llm.complete` (existing).
- Produces: `eval/results.json` `metrics` gains `prompt_tokens`, `completion_tokens`, `cached_tokens`, `total_tokens`, `llm_calls`; console report gains a Tokens block. No runner unit test exists by repo pattern — verified by Step 6 (full pytest) and Step 7 (live run).

- [ ] **Step 1: Extend the imports**

In `scripts/run_eval.py`, add `sum_usage` to the existing `alokasi_agent.eval` import block (lines 30-35):

```python
from alokasi_agent.eval import (
    aggregate,
    load_cases,
    load_fixture,
    score_turn,
    sum_usage,
)
```

Add after that block:

```python
from alokasi_agent.llm import complete as default_complete
```

- [ ] **Step 2: Add the token-row labels constant**

After the existing `MANUAL_CHECK_ID = "oos-005"` constant (line 53), add:

```python
# (label, metric key) pairs printed in the Tokens block.
TOKEN_KEYS = (
    ("prompt tokens", "prompt_tokens"),
    ("completion tokens", "completion_tokens"),
    ("cached prompt tokens", "cached_tokens"),
    ("total tokens", "total_tokens"),
    ("llm calls", "llm_calls"),
)
```

- [ ] **Step 3: Add the Tokens block to `print_report`**

In `print_report`, right after the line printing `api errors` (currently line 112: `print(f"  {'api errors':<23}: {metrics['api_error_count']}")`) and before the `if baseline:` per-case section, insert:

```python
    print("\nTokens")
    for label, key in TOKEN_KEYS:
        line = f"  {label:<23}: {metrics.get(key, 0)}"
        if baseline:
            old = baseline.get("metrics", {}).get(key)
            if old is not None:
                line += f" (baseline {old}, delta {metrics[key] - old:+d})"
        print(line)
```

(`baseline` is already loaded earlier in `print_report`; old baselines lack these keys, so the delta is skipped until the next `--update-baseline`.)

- [ ] **Step 4: Add the counting wrapper in `main()`**

In `main()`, immediately before the `for number, (case, now, fixture) in enumerate(prepared, start=1):` loop (currently line 207), insert:

```python
    usage_rows: list[dict[str, Any]] = []

    def counting_complete(messages, tools=None):
        # Record every API call's usage (an FR-05 retry = two rows).
        response = default_complete(messages, tools=tools)
        usage_rows.append(response.get("usage") or {})
        return response
```

- [ ] **Step 5: Inject the wrapper and merge totals**

In the same loop, add `complete=counting_complete` to the existing `run(...)` call (currently lines 214-221):

```python
                envelope, history = run(
                    turn["user"],
                    user_name=case["user_name"],
                    employees=fixture["employees"],
                    projects=fixture["projects"],
                    history=history,
                    now=now,
                    complete=counting_complete,
                )
```

After `metrics = aggregate(all_scores, api_errors)` (currently line 247), insert:

```python
    metrics.update(sum_usage(usage_rows))
    metrics["llm_calls"] = len(usage_rows)
```

- [ ] **Step 6: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: all tests pass (nothing in the suite imports `run_eval`, so this only guards against accidental breakage).

- [ ] **Step 7: Live verification run**

Run: `.venv\Scripts\python.exe scripts\run_eval.py --limit 1`
(needs `OPENAI_API_KEY` in `.env`; spends 1-2 API calls)
Expected:
- Console shows a `Tokens` block with `prompt tokens`, `completion tokens`, `cached prompt tokens`, `total tokens` > 0 and `llm calls` >= 1; no baseline delta yet (old baseline has no token keys).
- `eval/results.json` `metrics` contains all five new keys.
