# Design: FR-07 clarification loop

- Date: 2026-10-01
- Status: approved by the user (option A for the live check).
- FRD ref: FR-07 (§9, Milestone 3). Done-condition: a partial message
  followed by an answer produces a complete call.

## Gap analysis

The behavior already exists from delivered work:

- **Detect missing/ambiguous fields → ask, don't call**: prompt instruction #4
  plus examples 2–3 ("Untuk proyek apa alokasi ini?", "Rizka yang mana...").
- **Short conversation state**: `run()` history threading (FR-04).
- **Merge the answer**: the model combines the answer with history; FR-05
  rejects any incomplete tool call as a safety net (model then asks instead —
  already covered by `test_invalid_then_text_reply_is_normal_text`).

Missing: proof of the done-condition (no test, no live check) and a test pin
on the clarification instruction itself. **No `src/` changes.**

## Decisions

1. `tests/test_agent.py::test_partial_message_then_answer_produces_complete_call`
   — deterministic stubbed conversation: turn 1 partial message → text
   question; turn 2 answer + `history=` → complete six-field tool call;
   asserts turn 2's request carries system + prior turns.
2. `tests/test_prompt.py` — pin the marker `"ask one short clarifying
   question"` (FR-06 marker convention).
3. `scripts/smoke_agent.py` gains a `--partial` flag (editing an existing
   file, interactive `input()` exactly like `smoke_llm.py`):
   - sends a partial message ("besok aku ngerjain modul PPN jam 1 sampai jam 4"
     — project missing, "aku" = logged-in user);
   - every non-call turn prints the model's question and reads the answer
     from stdin (up to 6 turns, since confirmation is also a turn);
   - default mode (no flag) is unchanged: same message, follow-up "ya",
     PRD-sample comparison — FR-04 behavior preserved;
   - exit 0 iff the call contains all six non-empty fields (the date is
     relative, so no fixed-sample comparison in this mode).
4. FRD: FR-07 delivery annotation.

## Verification

- `.venv\Scripts\python.exe -m pytest` green.
- Live: `.venv\Scripts\python.exe scripts\smoke_agent.py --partial` with
  piped/typed answers; exit 0.

## Out of scope

- FR-08 edge cases, FR-09 fuzzy matching, FR-10 (confirmation is already a
  prompt rule but its FR lands separately).
- No prompt or `src/` changes.
