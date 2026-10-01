# Design: Simple rewrite of the delivered code (Approach 1)

- Date: 2026-10-01
- Scope: only the code already delivered for FR-01, FR-02, FR-04. No new FRs.
- Status: approved by the user.

## Goals

- Simplest possible solution that works. Beginner-readable.
- Plain functions over classes. No classes, no abstractions, no error handling that was not asked for.
- Keep a third-party library only while kept code still uses it; remove dependencies that become unused.
- Keep behavior equivalent; keep tests and the golden schema file green.
- Only make new files if needed.

## Decisions

### `src/alokasi_agent/schema.py`

- `CREATE_ALOKASI_DESCRIPTION` stays as-is.
- `CREATE_ALOKASI_TOOL` becomes a hand-written plain dict. Its `input_schema` is
  copied byte-identical from `tests/golden/create_alokasi_input_schema.json`, so the
  golden snapshot test passes unchanged.
- Pydantic models are removed. Nothing at runtime validates arguments today
  (that is FR-05, unbuilt), so `CreateAlokasiArgs` validation rules only ever
  ran in tests.
- The response envelope is no longer a model; `agent.run()` builds a plain dict.

### `src/alokasi_agent/llm.py`

- `LLMConfig` dataclass and `LLMClient` class are replaced by two plain functions:
  - `load_config() -> dict` reading the same env vars as today
    (`OPENAI_API_KEY`, `ALOKASI_MODEL`, `ALOKASI_TEMPERATURE`, `ALOKASI_TIMEOUT`,
    `ALOKASI_REASONING_EFFORT`, `OPENAI_BASE_URL`). Keeps the single
    `ValueError` when `OPENAI_API_KEY` is missing (an existing test asserts it).
  - `complete(messages, tools=None, config=None) -> dict` creates `OpenAI(...)`
    per call and returns `response.model_dump()`, so everything downstream is
    plain dicts.
- `to_openai_tools(tool)` stays unchanged.

### `src/alokasi_agent/prompt.py`

- Untouched; it is already plain functions.

### `src/alokasi_agent/agent.py`

- `run(raw_message, *, user_name, employees, projects, history=None, user_id=None,
  now=None, complete=None) -> tuple[dict, list]`.
- The injectable `client` object is replaced by an optional `complete` function
  `(messages, tools) -> dict`; tests pass a stub function.
- Reads `response["choices"][0]["message"]` as a dict.
- Envelope is a plain dict with keys `success`, `type`, `function_name`,
  `arguments`, `raw_message`, `user_id`, `reply`.
- Routing (`function_call` vs `text`) and history threading behave exactly as before.

### Tests

- `tests/test_agent.py`: `StubClient` class becomes a `make_stub(replies, calls)`
  plain function returning a fake `complete`; envelope assertions switch from
  attribute access to dict access. Same behaviors covered.
- `tests/test_llm.py`: config tests target `load_config()` dict keys; `complete`
  tests monkeypatch a small test-local fake for `OpenAI`; `to_openai_tools`
  test unchanged. The non-numeric env override test asserts `ValueError`
  without a custom message (the message now comes from `float()`).
- `tests/test_schema.py`: keeps tool-shape, format, required-field, and golden
  tests against the dict; drops Pydantic-only validation tests and envelope
  model tests (obsolete; FR-05 will add real validation later).
- `tests/test_prompt.py` and `tests/golden/*.json`: unchanged.

### Scripts

- `scripts/smoke_agent.py` / `scripts/smoke_llm.py`: switch to the `complete()`
  function and dict responses; `load_dotenv` stays.
- `scripts/update_golden.py`: unchanged logic (still reads `CREATE_ALOKASI_TOOL`).

### Dependencies (`pyproject.toml`)

- Remove `pydantic` (becomes unused).
- Keep `openai`, `tzdata`, `python-dotenv`, and dev dep `pytest` (all still used).

### New file: `AGENTS.md`

- Repo-root standing instructions so any future session follows the same rules:
  simplest solution, plain functions, no unasked features/abstractions/error
  handling, minimal changes, comment non-obvious code, prefer stdlib, keep a
  library only while used, work FRD step by step.

## Verification

1. `.venv\Scripts\python.exe -m pytest` — all tests green.
2. Optional live check: `.venv\Scripts\python.exe scripts\smoke_agent.py`
   (needs `OPENAI_API_KEY`) — FR-04 done-condition: sample arguments match.

## Out of scope

- FR-05 validation/retry, FR-07 clarification merge, FR-08..FR-15 — future work,
  one FR at a time in the same simple style.
- README expansion, git commits (unless the user asks).
