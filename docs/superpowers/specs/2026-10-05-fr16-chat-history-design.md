# Design: FR-16 chat history in the envelope

- Date: 2026-10-05
- Status: approved by the user (full text history now, optimize later).
- FRD ref: FR-16 (§9, Milestone 3). Done-condition: a two-turn conversation
  (summary, then "Benar") where turn 2 reuses turn 1's envelope `history`
  produces the `create_alokasi` call.

## Gap analysis

`run()` already threads full-text history: it reads `history=`, and returns
`new_history` (prior turns + this user message + this reply's text) as the
second tuple element (FR-04). What is missing is the transport: the CI3
backend only receives the envelope dict, so it has no way to store history
and send it back on the next request. Without that, a confirmation like
"Benar" arrives with no context and the model cannot confirm the summary it
showed one turn earlier — a wasted round trip.

## Decisions

1. `src/alokasi_agent/agent.py` — one line: after `new_history` is built,
   set `envelope["history"] = new_history` before returning. Sits after the
   three-way routing, so `function_call`, `text`, and `error` envelopes all
   carry it (the error reason is an assistant turn — it is part of the
   conversation). Same list object as the tuple's second element; full text,
   no trimming or summarizing.
2. `tests/test_agent.py` — two tests:
   - `test_envelope_history_confirms_second_turn` (the FR-16 done-condition):
     turn 1 stub → text "Benar?"; turn 2 passes `env1["history"]` →
     request carries `["system", "user", "assistant", "user"]` and the reply
     is a `create_alokasi` call.
   - `test_envelope_carries_full_text_history`: `env["history"] == history`
     with roles `["user", "assistant"]`; plus a one-line assert that the
     error envelope carries it too (added to the existing error test).
3. FRD: no edit — §8.3 table already documents `history`; no delivered-note
   (user's call: skipped).

## Verification

- `.venv\Scripts\python.exe -m pytest` green.

## Out of scope

- Trimming/summarizing history (deliberately deferred: the loop is 2–4 short
  turns, so the extra tokens are small; the real cost driver is a wasted
  round trip, not history size).
- Storage: the backend stores the envelope `history` and sends it back
  (PRD §8.3, backend track).
- `scripts/smoke_agent.py` unchanged — it already threads history in-process.
