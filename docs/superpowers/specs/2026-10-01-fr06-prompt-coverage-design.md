# Design: FR-06 prompt coverage gap-fill

- Date: 2026-10-01
- Status: approved by the user.
- FRD ref: FR-06 (§9), already marked "Absorbed into prompt rules
  (2026-10-01)". This closes the variants the absorbed prompt does not yet
  mention.

## Gap analysis (FR-06 variant list vs `PROMPT_TEMPLATE`)

| Variant | Status before |
|---|---|
| "besok", "lusa", "kemarin", "Senin depan" | covered |
| "jam 09 pagi", "12 siang", "3 sore", "jam 8 malam" | covered |
| explicit "29 September 2026" | only in an example, not a rule |
| "09.00" (dot separator) | missing |
| range "09:00-12:00" | missing |
| year defaults to current year when left out | missing |

## Decisions

- Three additive lines in `PROMPT_TEMPLATE` (`src/alokasi_agent/prompt.py`),
  text only — no code changes, no new files:
  1. `tanggal` rule: written-out dates like "29 September 2026" →
     `2026-09-29`; if no year is given, use the current year.
  2. `jam` rule: "09.00" means the same as "09:00".
  3. `jam` rule: a range like "09:00-12:00" is jam_mulai-jam_selesai.
- `tests/test_prompt.py::test_rule_markers_present` gains one assertion per
  addition, so a later prompt edit cannot silently drop FR-06 coverage.
- FRD: append a coverage note to the existing FR-06 "Absorbed" annotation.

## Verification

- `.venv\Scripts\python.exe -m pytest` green.
- Live `.venv\Scripts\python.exe scripts\smoke_agent.py` still matches the
  PRD sample (it exercises "jam 09 pagi sampai 12 siang").

## Out of scope

- FR-06's original "unit tests cover Indonesian variants" done-condition
  stays superseded (FRD note); no code normalizer is built.
- FR-12 eval dataset, prompt rewriting/trimming (FR-14).
