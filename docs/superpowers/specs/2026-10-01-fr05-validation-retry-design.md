# Design: FR-05 validation, retry, and fallback

- Date: 2026-10-01
- Status: approved by the user.
- FRD ref: FR-05 (§9, Milestone 2). Done-condition: malformed LLM output never
  reaches the backend.

## Goals

- Same rules as the rewrite: plain functions, stdlib only, no abstractions,
  no unasked error handling, no new files.

## Decisions

### Validator — added to `src/alokasi_agent/schema.py`

`validate_arguments(arguments: str) -> list[str]` returns the list of
problems (empty = valid). Checked in order:

1. `json.loads` fails, or the result is not a dict.
2. Any of the six required fields missing, not a string, or blank after strip.
3. Unknown keys (the contract is exactly six arguments).
4. `tanggal`: shape `^\d{4}-\d{2}-\d{2}$` **and** `date.fromisoformat(...)`
   accepts it — rejects `2026-13-45` and `2026-9-29`.
5. `jam_mulai` / `jam_selesai`: shape `^\d{2}:\d{2}$`, hour ≤ 23,
   minute ≤ 59 — rejects `99:99`, `12:60`, `9:00`.
6. `jam_selesai` later than `jam_mulai` (compared as minutes).

Stdlib only — this is exactly the mechanism FR-05 describes; pydantic stays
removed. Error strings are Indonesian (they end up user-facing via `reply`).

### Retry — inside `agent.py`'s `run()`

- First response: if it is a text reply, behave exactly as today.
- If it is a tool call: validate. Valid → function_call envelope, one API
  call, no change from today.
- Invalid → append the assistant message (with its `tool_calls`) and one
  `{"role": "tool", "tool_call_id": ..., "content": "<errors>"}` message per
  tool call (the API requires a tool reply for every call), then call
  `complete()` a second time and validate again.
  - second reply is text → normal text envelope (model asked a question)
  - second tool call is valid → function_call envelope
  - second tool call still invalid → error envelope:
    `success: false`, `type: "error"`, `function_name: ""`, `arguments: ""`
    (never a partial call), `reply: "Data tidak valid setelah dicoba ulang: ..."`
- Exactly one retry (FRD says retry once). History keeps its user/assistant
  pair shape; on the error path the reason string is the assistant turn.

### Tests

- `tests/test_schema.py`: validator units — sample passes; malformed JSON,
  non-object, each bad date/time case, ordering, missing/blank/unknown fields
  produce errors.
- `tests/test_agent.py`: valid call → exactly 1 `complete` call; invalid→valid
  retries and succeeds (asserts the `tool` message carries the errors);
  invalid→invalid → error envelope (done-condition); invalid→text → text
  envelope. Stub tool calls gain an `id` field for the `tool` message.

### Docs

- FR-05 delivery annotation in `PRD_FRD_create_alokasi_agent.md` (repo
  convention).

## Out of scope

- FR-07 clarification merge, FR-08 edge cases, fuzzy matching (FR-09).
- Changing the prompt, the smoke scripts, or dependencies.
