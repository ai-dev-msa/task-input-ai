# Design: FR-12/FR-13 eval dataset runner and metrics

- Date: 2026-10-06
- Status: approved by the user (full plan in the session; executed as-is).
- FRD ref: FR-12 (dataset as JSONL, versioned, category-tagged) and FR-13
  (regression runner: field-level accuracy, exact-match rate, clarification
  precision, comparison with the previous run). FR-13's threshold is TBD, so
  this track is report-only: no CI workflow, no threshold gate.

## Gap analysis

- FR-12: `seeds.txt` already holds the 46 cases (single-line JSON objects =
  JSONL) with `category` and `split` on every case, but it lives as a `.txt`
  at the repo root and there is no fixture (the employee/project lists the
  agent needs) beside it.
- FR-13: nothing scores the agent. There is no runner, no metric
  definitions, no baseline to compare against.

## Decisions

### 1. Dataset: `eval/cases.jsonl`

- Byte-identical copy of `seeds.txt` (verified by file hash). Content is
  frozen: any change means a new fixture version and a re-baseline.
- 46 cases, 83 turns, unique ids. Splits: 34 dev / 12 test.
  Kinds: confirm 35, call 33, ask 12, drop_review 1, cancel 1, refuse 1.
- Case schema: `{id, category, difficulty, split, fixture, source, now,
  user_name, turns, notes}`; each turn = `{user, expect}`; every case has
  `fixture: "v1"` and a tz-aware `now`.

### 2. Fixture: `eval/fixtures/v1.json`

`{employees, projects, forbidden}`, derived once from the 46 cases:

- `employees` (58): every `user_name`, every gold `nama_karyawan`, every
  `tim_pekerjaan` member, plus the first-name-only references the cases
  require to resolve (`Hafiz Akbar`, `Siti Aminah`) and the two Rizkas
  (`Rizka Amelia`, `Rizka Putri`) that assignee-003 needs for its negation.
  Single-fit names stay single-fit: one Fajar, one Hendra, one Lintang, one
  Farah, one Hafiz, one Tasya, one Bima, one Gilang, one Siti.
- `projects` (21): every gold `nama_proyek`, the two projects only named in
  ask-turn messages (`Riset Pasar Segmen Muda 2026`,
  `Penyusunan SOP Perusahaan 2026`), and the three OPRS projects
  (`OPRS Divisi IT/WIN/HRD 2026`) that entity-007's `OPRS Divisi 2026`
  must be ambiguous between. `OPRS Divisi 2026` itself is not a project.
- `forbidden`: `["Sukma*", "Joko", "Ekspansi Pasar Eropa 2026"]` per the
  case notes. An entry with a trailing `*` is a prefix match, any other
  entry a substring match, against `employees ∪ projects`; the fixture must
  match nothing.
- Frozen: any change to the fixture means a new version directory
  (`eval/fixtures/v2.json`) and a re-baseline.

### 3. `src/alokasi_agent/eval.py` — pure functions

- `load_cases(path)`, `load_fixture(path)`: JSONL/JSON readers; a bad line
  raises with its line number (operational error, see runner).
- `parse_summary(reply) -> list[dict]`: the confirm/drop_review summary
  parser. Split the reply into lines, split each line on `|`:
  - `<5` parts → line ignored (e.g. the drop_review notice);
  - `5` parts → `[nama_karyawan, nama_proyek, tanggal, jenis_pekerjaan,
    jam_mulai-jam_selesai]`; `6` adds `review`; `7` adds `tim_pekerjaan`;
    `>7` → unparseable;
  - strip trailing `Benar?` / `Salah?` / `.` from the last part;
  - `tanggal` must match `YYYY-MM-DD`, the time part `HH:MM-HH:MM`, the
    first five parts non-empty — otherwise unparseable;
  - unparseable ⇒ return `[]` (on a confirm turn that scores 0 fields).
- `classify(envelope) -> "call" | "confirm" | "ask" | "other"`:
  `function_call` → `call`; else summary parses → `confirm`; else `?` in
  the reply → `ask`; else `other`. The hard rule falls out of the order:
  an `ask` never carries a call and never emits a summary.
- `score_turn(expect, envelope) -> dict`: one turn's scores (below).
- `aggregate(scores, api_errors) -> dict`: metric totals over scored turns.

### 4. Metrics (report-only)

Decision accuracy over all turns (4 classes):

- expected: `confirm`/`drop_review` → `confirm`, `call` → `call`,
  `ask` → `ask`, `cancel`/`refuse` → `other`;
- predicted: `classify(envelope)`.

Row-bearing turns (expected `confirm`/`drop_review`/`call`):

- predicted rows: `call` → parse `envelope["arguments"]` (object or array);
  `confirm`/`drop_review` → `parse_summary(reply)`; anything else → none;
- exact match: predicted rows == expected rows (list of dicts, order and
  keys both matter, so a phantom `"review": ""` fails);
- field accuracy: rows aligned by index; per pair the denominator is the
  union of keys and a field counts only when both sides carry it and they
  are equal; missing/extra rows add their full key counts to the
  denominator;
- optional-field recall (`review`, `tim_pekerjaan`): of the expected
  optional fields, the share whose aligned predicted row carries a
  non-empty value for that key.

Clarification precision/recall: `ask` turns from the confusion matrix
(predicted-`ask` denominator for precision, expected-`ask` for recall).

API errors: a `run()` exception aborts that case, is counted
(`api_error_count`) and excluded from every denominator.

Report also carries a 4×4 confusion matrix, a per-category table, and the
per-case counts.

### 5. `scripts/run_eval.py` — runner

- `load_dotenv()` first (same as `scripts/smoke_agent.py`); missing
  `OPENAI_API_KEY` or unparseable cases/fixture ⇒ non-zero exit.
- Filters: `--split`, `--category`, `--only` (comma-separated ids),
  `--limit`.
- Per case: resolve `eval/fixtures/{fixture}.json`, then per turn call
  `run(..., now=datetime.fromisoformat(case["now"]),
  user_name=..., employees=..., projects=..., history=...)` and thread the
  returned history turn-to-turn; score each turn.
- Print: headline metrics, Δ against `eval/baseline.json` (when present),
  regressed/improved case ids (per-case score =
  `(decision_correct + row_exact + field_correct) / all denominators`,
  compared only for ids present in both files), per-category table,
  decision confusion matrix, failure lines (expected vs predicted plus the
  reply), and the `oos-005` reply tagged `manual check` (the poem cannot be
  caught by substring checks).
- Write `eval/results.json` as `{metrics, cases}`; `--update-baseline`
  copies it over `eval/baseline.json` (committed by hand later).
- Exit 0 even when accuracy is bad — only operational errors exit non-zero.

### 6. Tests: `tests/test_eval.py`

No API calls; envelope dicts are hand-built (the stub pattern of
`tests/test_agent.py` is not needed because `score_turn` takes an envelope
directly). Coverage:

- parser edge cases (5/6/7 parts, `Benar?`/`Salah?`/`.` stripping,
  drop_review notice line ignored, bad date/time ⇒ `[]`, multi-row replies);
- `score_turn` per kind (confirm, call multi-row, ask-vs-confirm,
  phantom `review: ""`, row-count mismatch, drop_review, cancel, refuse);
- `aggregate` math against hand-built score dicts;
- classification rules incl. the ask hard rule;
- dataset integrity: 46 lines, unique ids, kind counts, splits, fixtures
  resolve, `now` tz-aware;
- `forbidden ∩ (employees ∪ projects) = ∅`.

## Verification

- `.venv\Scripts\python.exe -m pytest` green.
- Live smoke: `.venv\Scripts\python.exe scripts\run_eval.py --only timefmt-002`.
- Full run: `.venv\Scripts\python.exe scripts\run_eval.py --update-baseline`
  (46 cases, ~100–140 API calls, `OPENAI_API_KEY` in `.env`).

## Out of scope

- No CI workflow, no accuracy threshold gate (FR-13 threshold TBD).
- No FR-14/FR-15 work; no FRD edits.
- No edits to `seeds.txt` content; no commits (the user commits).
- `eval/results.json` is gitignored; `eval/baseline.json` is not.
