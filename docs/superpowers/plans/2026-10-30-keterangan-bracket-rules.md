# Plan: rename `review` → `keterangan` and add status-bracket placement rules

Agreed with the user on 2026-10-30. Binding spec: the seven-part agreement in
the PRD/FRD decision note this plan adds (Task 8) plus the five placement
rules below. Everything in this plan is already decided; execute it as
written.

## Spec (the five placement rules, user-approved)

1. A bracket written together with the task name stays in `jenis_pekerjaan`
   exactly as typed.
2. A bracket beside a label word (review, hasil, keterangan) → `keterangan`.
3. A bare/unclear bracket (including the word "review" read as part of the
   task name, e.g. "review laporan kas [2/1/1/0]") → one short question
   "Itu untuk jenis pekerjaan atau keterangan?"
4. The bot only copies the bracket; it never recalculates or corrects it.
5. Never auto-append "Done" / "not done".

Field key is `keterangan` everywhere (matches the CI3 column; `main.py` forwards
rows verbatim). The format gloss `[total / target today / finished / remaining]`
IS in the prompt, immediately followed by the guard that the numbers never
decide placement. Ask wording is Indonesian using the field name. The 3-day
window stays; its notice wording becomes "Keterangan hanya bisa diisi...".

## Context

- Branch `dev`, clean tree, HEAD `9fa5515`. Baseline pytest is red:
  24 failed, 3 errors, 141 passed — ALL pre-existing stale expectations
  (commit 152faf8 deleted `tim_pekerjaan` from `src/` only; 451502c changed
  blank-optional semantics; bcf5dd4/9fa5515 changed name-resolution wording;
  the `_SUMMARY_OPTIONAL` string bug). Green at the end is the goal state.
- The user approved updating those stale tests/eval data and removing
  test_main_chat's dead `main.get_employees` fixture patch to reach a green
  pytest. Do NOT redo the tim_pekerjaan deletion in `src/` (it is already gone).
- `_SUMMARY_OPTIONAL = ("review")` in `prompt.py` is a STRING, not a tuple:
  `zip("review", parts[5:])` stores the field under key `"r"`. Verified:
  `_same_rows(emitted_review_call, parsed_row)` → `False`. The tuple fix is
  mandatory — it is what makes the rename actually deliver `keterangan`.

## Global Constraints

- Test command: `.venv\Scripts\python.exe -m pytest` (full suite). Per-task
  commands are scoped and named in each task below.
- AGENTS.md: simplest solution, plain functions, minimal edits, no
  third-party deps, no commits unless the user asks. NO COMMITS in this run —
  so task-done ledger ranges show the same SHA on both ends; that is expected.
- Live checks need `OPENAI_API_KEY`: `scripts\smoke_agent.py`. If the key is
  absent, say so; do not block.
- Leave untouched: `main.py`, `docs/superpowers/specs|plans/*` (historical),
  `docs/superpowers/sdd/` sibling workspaces, `eval/fixtures/v1.json`
  (fixture still valid: its `Review Kontrak Vendor 2026` project is unrelated).
- Scripts (`scripts/*.py`) contain no `review`/`tim_pekerjaan` references
  (verified). No changes needed there.

## Interfaces (pre-flight)

- Task 1 produces parse key `keterangan` ← consumed by Task 4 (eval scoring
  fields), Task 5 (gold row keys), Task 6 (row-guard fixtures). All use the
  same string. No conflict.
- Task 2 produces `OPTIONAL_FIELDS = ("jam_selesai", "keterangan")` ← consumed
  by agent's null/blank strip (no test change) and Task 6's null-optional
  tests. No conflict.
- Task 3's summary format `[ | keterangan]` ← consumed by Task 1's
  `parse_summary` docstring. Task 1 runs first; parse accepts any 6th part
  regardless of the label, and Task 1's test command is scoped. No conflict.
- Task 5's dataset counts are produced and consumed inside Task 5 (case edits
  + count tests), red first, then green together.

Pre-flight: no conflicts.

---

## Task 1: `parse_summary` stores `keterangan` (tuple fix + rename)

**Files:** `src/alokasi_agent/prompt.py`, `tests/test_eval.py`

RED — edit `tests/test_eval.py` first:

1. Replace `test_parse_summary_keeps_review_and_tim` with:

```python
def test_parse_summary_keeps_keterangan():
    line = (
        "Ratna Kusumawati | Pengembangan Produk Baru 2026 | 2026-09-29 "
        "| ngerjain stress test aplikasi | 09:00-12:00 "
        "| [1/1/1/1]. Benar?"
    )
    rows = parse_summary(line)
    assert len(rows) == 1
    assert rows[0]["keterangan"] == "[1/1/1/1]"
    assert "tim_pekerjaan" not in rows[0]
```

2. In `test_parse_summary_ignores_drop_review_notice` change the first reply
   line to `"Keterangan hanya bisa diisi maksimal 3 hari setelah tanggal tugas.\n"`
   and the assert to `assert "keterangan" not in rows[0]`.
3. In `test_parse_summary_no_summary` change
   `"Review bisa diisi maks 3 hari.\nBenar?"` → `"Keterangan bisa diisi maks 3 hari.\nBenar?"`.

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -k parse_summary -q`
Expected: RED — `test_parse_summary_keeps_keterangan` fails (actual key is `"r"`).

GREEN — edit `src/alokasi_agent/prompt.py`:

- Line 13: `_SUMMARY_OPTIONAL = ("review")` → `_SUMMARY_OPTIONAL = ("keterangan",)`
- Line 214 docstring: `plus ' | review' when present.` → `plus ' | keterangan' when present.`

Run the same command. Expected: all `parse_summary` tests pass.

Test command for task-done:
`.venv\Scripts\python.exe -m pytest tests/test_eval.py -k parse_summary`

---

## Task 2: schema rename + golden regeneration

**Files:** `src/alokasi_agent/schema.py`, `tests/test_schema.py`,
`tests/golden/create_alokasi_input_schema.json`

RED — edit `tests/test_schema.py`:

1. `test_validate_accepts_optional_fields`: replace the call with
   `validate_arguments(as_json(keterangan="[1/1/1/0]")) == []` (drop `tim_pekerjaan`).
2. Rename `test_validate_rejects_blank_optional_field` →
   `test_blank_optional_fields_mean_not_provided`, params become
   `as_json(keterangan="")`, `as_json(keterangan="   ")`, `as_json(jam_selesai="")`,
   `as_json(jam_selesai="   ")`, and the assert becomes
   `assert validate_arguments(payload) == []` (blank = "not provided" since 451502c).
3. `test_explicit_null_on_optional_fields_is_accepted`: `"review": None` →
   `"keterangan": None`, delete the `"tim_pekerjaan": None` line.
4. DELETE `test_empty_string_on_optional_field_still_errors` — its premise
   (blank errors) was invalidated by 451502c; coverage now lives in the
   inverted blank test from step 2.

Run: `.venv\Scripts\python.exe -m pytest tests/test_schema.py -q`
Expected: RED — keterangan params fail ("keterangan bukan argumen"), golden
snapshot fails; blank `jam_selesai` params may already pass (stale-cleanup sibling).

GREEN — edit `src/alokasi_agent/schema.py`:

- `OPTIONAL_FIELDS = ("jam_selesai", "review")` → `("jam_selesai", "keterangan")`
- Property block (keep the file's alphabetical order: insert after
  `jenis_pekerjaan`, delete the old `review` block after `nama_proyek`):

```python
            "keterangan": {
                "description": "Status/hasil pekerjaan dalam format [a/b/c/d], contoh: [2/1/1/0]",
                "minLength": 1,
                "title": "Keterangan",
                "type": "string",
            },
```

Then regenerate golden: `.venv\Scripts\python.exe scripts\update_golden.py`
Run: `.venv\Scripts\python.exe -m pytest tests/test_schema.py -q`
Expected: all pass (golden test green after regen).

Test command for task-done: `.venv\Scripts\python.exe -m pytest tests/test_schema.py`

---

## Task 3: prompt field rules, flow renames, examples

**Files:** `src/alokasi_agent/prompt.py`, `tests/test_prompt.py`

RED — edit `tests/test_prompt.py` first:

1. `test_optional_field_rules_present` — replace ALL its asserts with:

```python
def test_optional_field_rules_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "keterangan (optional):" in out
    assert '"[a/b/c/d]"' in out
    assert "a work log the user writes" in out
    assert "The numbers do NOT decide where the" in out
    assert "never recalculate or correct" in out
    assert 'never add "Done" or "not done"' in out
    assert "with a label word (review, hasil, keterangan) -> keterangan:" in out
    assert 'exactly as typed: "Verifikasi laporan kas [1/1/0/1]" -> jenis_pekerjaan' in out
    assert '"review laporan kas [2/1/1/0]"' in out
    assert 'atau keterangan?" and put it where the user says.' in out
    assert "max 3 days after the task date" in out
    assert "Always include every key in the call." in out
    assert 'Never pass "" for them.' in out
    assert "do not ask or guess a length" in out
    assert "review (optional):" not in out
    assert "tim_pekerjaan" not in out
```

2. `test_missing_optional_end_time_never_prompts_ask` line 133:
   `"never add jam_selesai or review to"` → `"never add jam_selesai or keterangan to"`.
3. `test_name_resolution_markers_present` line 100: replace
   `assert "each resolved with" in out` with
   `assert "use only the spelling the tool returned" in out`.
4. Sweep: `Select-String -Path tests\test_prompt.py -Pattern "review"` — every
   remaining `review` assertion must be about prompt text (rename to
   `keterangan`), never about the label word list (that one stays "review" by
   spec; the label list assertion is in step 1).

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompt.py -q`
Expected: RED — new markers absent, old markers still asserted.

GREEN — edit `src/alokasi_agent/prompt.py`:

a) Flow line 49: `jam_selesai (end time or duration), review.` → `..., keterangan.`
b) Lines 52-53: `never add jam_selesai or review to` → `never add jam_selesai or keterangan to`
c) Line 65: `jam_mulai-jam_selesai[ | review]. Benar?` → `jam_mulai-jam_selesai[ | keterangan]. Benar?`
d) Line 74: `date, times, and review;` → `date, times, and keterangan;`
e) Replace lines 109-116 (jenis_pekerjaan rule through "Never pass ..." line)
   with EXACTLY (indentation significant — assertion fragments depend on where
   the lines wrap):

```
jenis_pekerjaan: the user's wording, trimmed. Do not rephrase, translate, or
  add detail. A status bracket written together with the task name stays here,
  exactly as typed: "Verifikasi laporan kas [1/1/0/1]" -> jenis_pekerjaan
  "Verifikasi laporan kas [1/1/0/1]".
keterangan (optional): a status bracket "[a/b/c/d]" = [total / target today /
  finished / remaining] — a work log the user writes. Copy the bracket exactly
  as typed: the numbers can be any whole numbers, never recalculate or correct
  them, never add "Done" or "not done". The numbers do NOT decide where the
  bracket goes: [5/2/2/0] can be a morning plan or an evening result, so choose
  only by the rules below. Where the bracket goes:
  - with a label word (review, hasil, keterangan) -> keterangan:
    "review [1/1/1/0]" -> keterangan "[1/1/1/0]".
  - with the task name, no label -> jenis_pekerjaan (rule above), keterangan null.
  - no task name and no label, or a label word that reads as part of the task
    name ("review laporan kas [2/1/1/0]") -> ask "Itu untuk jenis pekerjaan
    atau keterangan?" and put it where the user says.
  Only for tasks dated today or up to 3 days ago; if older, say in one line
    that keterangan can only be entered max 3 days after the task date, set it
    to null, and continue.
Always include every key in the call. Pass null for jam_selesai, keterangan
  when the user gave none. Never pass "" for them.
```

(Ruling: the collision clause in bullet 3 — `or a label word that reads as
part of the task name ...` — carries spec rule 3, which the approved verbatim
text did not spell out; without it the example and eval case for
"review laporan kas" would contradict bullet 1. Cost if wrong: ~15 prompt
tokens.)

f) Line 135 example note: `(jam_selesai "12:00", review null)` →
   `(jam_selesai "12:00", keterangan null)`
g) Replace the stress-test example (lines 153-156) with — team slot dropped,
   trailing "Done" shown NOT carried into the summary:

```
"hari ini stress test aplikasi jam 9-12, proyek Pengembangan Produk Baru 2026,
review [1/1/1/0] Done"
-> Dimas Eka Priyadi | Pengembangan Produk Baru 2026 | 2026-09-30 | stress test
   aplikasi | 09:00-12:00 | [1/1/1/0]. Benar?
```

h) Replace the Sinta/Raden example summary lines (brackets now glue into
   jenis_pekerjaan; input unchanged):

```
-> Sinta Maulida | Migrasi Server Cloud 2026 | 2026-09-30 | [1/1/0/1] Verifikasi
   laporan kas | 16:00-16:30
   Raden Mahesa | Migrasi Server Cloud 2026 | 2026-09-30 | [1/1/0/2] Rekap mutu
   supplier | 16:30-17:00. Benar?   (after "ya": two calls, same reply)
```

i) Insert AFTER the Sinta/Raden example (bracket examples stay together):

```
"hari ini review laporan kas [2/1/1/0] jam 9-11, proyek Penyusunan SOP
Perusahaan 2026"
-> "Itu untuk jenis pekerjaan atau keterangan?"
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompt.py -q`
Expected: all pass. Also run the full suite once for information:
`.venv\Scripts\python.exe -m pytest -q` — remaining reds must be ONLY
test_agent/test_eval/test_main_chat/test_schema leftovers not yet done
(they are Tasks 4-7).

Test command for task-done: `.venv\Scripts\python.exe -m pytest tests/test_prompt.py`

---

## Task 4: eval scoring uses `keterangan`

**Files:** `src/alokasi_agent/eval.py`, `tests/test_eval.py`

RED — edit `tests/test_eval.py`:

1. `test_score_drop_review_counts_as_confirm`: gold filter
   `if key != "review"` → `if key != "keterangan"`; reply first line →
   `"Keterangan hanya bisa diisi maksimal 3 hari setelah tanggal tugas.\n"`.
2. Rename `test_score_phantom_empty_review_fails_exact_and_field` →
   `test_score_phantom_empty_keterangan_fails_exact_and_field`; inside,
   `phantom = dict(ROW, review="")` → `dict(ROW, keterangan="")` (counts 7/6 stay).
3. `test_score_optional_field_recall` — replace with:

```python
def test_score_optional_field_recall():
    gold = dict(ROW, keterangan="[1/1/1/1]")
    expect = {"kind": "confirm", "rows": [gold]}
    missing = score_turn(expect, text_envelope(SUMMARY_LINE))
    assert missing["optional_total"] == 1
    assert missing["optional_correct"] == 0
    assert missing["row_exact"] is False

    line = (
        "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN "
        "| 09:00-12:00 | [1/1/1/1]. Benar?"
    )
    present = score_turn(expect, text_envelope(line))
    assert present["optional_correct"] == present["optional_total"] == 1
    assert present["row_exact"] is True
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -k "score or classify" -q`
Expected: RED — `test_score_optional_field_recall` fails (eval still tracks
`review`/`tim_pekerjaan` → `optional_total == 0`).

GREEN — edit `src/alokasi_agent/eval.py` lines 29-31:

```python
# Optional fields tracked by score_turn's optional-field recall (parse_summary
# lives in prompt.py and parses the same slot).
OPTIONAL_FIELDS = ("keterangan",)
```

Run the same command. Expected: all pass.

Test command for task-done:
`.venv\Scripts\python.exe -m pytest tests/test_eval.py -k "score or classify"`

---

## Task 5: eval cases rewritten + dataset counts

**Files:** `eval/cases.jsonl`, `tests/test_eval.py`

RED — edit `tests/test_eval.py`:

1. Rename `test_dataset_has_47_cases_with_unique_ids` →
   `test_dataset_has_49_cases_with_unique_ids`; both asserts 47 → 49.
2. `test_dataset_kind_and_split_counts` expected kinds →

```python
    assert dict(kinds) == {
        "confirm": 37,
        "call": 35,
        "ask": 13,
        "drop_review": 1,
        "cancel": 1,
        "refuse": 1,
    }
    assert dict(Counter(case["split"] for case in cases)) == {"dev": 36, "test": 13}
```

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -k dataset -q`
Expected: RED — still 47 cases / old counts.

GREEN — edit `eval/cases.jsonl` (one JSON object per line; keep the file's
`json.dumps(..., ensure_ascii=False)` default-separator style). Transforms by
id — apply to BOTH the confirm row and the call row where present:

- **review-002**: key `review` → `keterangan`, value `"[1/1/1/1] done"` →
  `"[1/1/1/1]"` (bare bracket: the user's trailing "done" is not carried);
  DELETE the `tim_pekerjaan` key. Notes →:
  `"Label word 'review' puts the bracket in keterangan, copied verbatim; the trailing 'done' is neither copied nor re-added. The team mention ('tim Eko sama Mega') is not a field anymore: no tim key, and it must not leak into jenis_pekerjaan. Task dated 1 day ago, so keterangan is kept."`
- **review-003**: `review` → `keterangan`, value `"[1/0/1/1] not done"` →
  `"[1/0/1/1]"`. Notes →:
  `"Boundary: 2026-09-27 is exactly 3 days before today, so keterangan is still kept. The bracket is copied verbatim, including the 0; the 'belum done' wording is not appended."`
- **review-004**: rows/calls unchanged (they never carry the key). Notes →:
  `"Boundary: 2026-09-26 is 4 days ago, one day past the window. The agent says in one short line that keterangan can only be entered up to 3 days after the task date, drops it, and still shows the row for confirmation without keterangan. It must not ask the user what to do. The final call has no keterangan key."`
- **review-005**: turn 1 user →
  `"besok aku ngecek dokumen kontrak jam 9-11, proyek Pembukaan Cabang Surabaya 2026"`;
  DELETE `tim_pekerjaan` from rows/calls. Notes →:
  `"Plain confirm with no optional fields: neither keterangan nor any empty value appears in the row or the call."`
- **review-006**: turn 1 user →
  `"hari ini review laporan kas [2/1/1/0] jam 9 sampe 11, proyek Riset Pasar Segmen Muda 2026"`;
  expect → `{"kind": "ask", "asks_about": ["jenis_pekerjaan", "keterangan"]}`.
  Notes →:
  `"Spec rule 3: the word 'review' reads as part of the task name, so the bracket is unclear. The agent asks one short question ('Itu untuk jenis pekerjaan atau keterangan?') instead of guessing a field. Single turn: no confirm and no call."`
- **review-007**: turns → SINGLE turn (delete the "ya"/call turn): user stays
  `"hari ini aku ngecek kualitas sampel batch 12 jam 8 sampe 10, [2/1/0/1] udah kelar semua, proyek Audit Mutu ISO 2026"`; expect →
  `{"kind": "ask", "asks_about": ["jenis_pekerjaan", "keterangan"]}`.
  Notes →:
  `"Spec rule 3 (bare bracket): the bracket stands alone after the times — no label and no task name next to it — so the agent asks one short question instead of guessing. 'batch 12' is part of the task, not a time or a number to convert. Single turn: no confirm and no call."`
- **review-008** NEW — insert as its own line immediately AFTER review-007:

```json
{"id": "review-008", "category": "review_and_team", "difficulty": "hard", "split": "dev", "fixture": "v1", "source": "written", "now": "2026-09-30T14:05:00+07:00", "user_name": "Ratna Kusumawati", "turns": [{"user": "hari ini Verifikasi laporan kas [1/1/0/1] jam 16 sampe 16.30, proyek Pengembangan Produk Baru 2026", "expect": {"kind": "confirm", "rows": [{"nama_karyawan": "Ratna Kusumawati", "nama_proyek": "Pengembangan Produk Baru 2026", "tanggal": "2026-09-30", "jenis_pekerjaan": "Verifikasi laporan kas [1/1/0/1]", "jam_mulai": "16:00", "jam_selesai": "16:30"}]}}, {"user": "ya", "expect": {"kind": "call", "calls": [{"nama_karyawan": "Ratna Kusumawati", "nama_proyek": "Pengembangan Produk Baru 2026", "tanggal": "2026-09-30", "jenis_pekerjaan": "Verifikasi laporan kas [1/1/0/1]", "jam_mulai": "16:00", "jam_selesai": "16:30"}]}}], "notes": "Spec rule 1: the bracket is written together with the task name and has no label word, so it stays in jenis_pekerjaan exactly as typed and keterangan stays null (no keterangan key). 'jam 16 sampe 16.30' reads as 16:00-16:30; the digits inside the bracket are never treated as times or converted."}
```

- **review-009** NEW — insert immediately AFTER review-008:

```json
{"id": "review-009", "category": "review_and_team", "difficulty": "hard", "split": "test", "fixture": "v1", "source": "written", "now": "2026-09-30T14:05:00+07:00", "user_name": "Eka Mulyani", "turns": [{"user": "kemarin aku bikin laporan penjualan jam 9 sampe 11, hasil [2/1/1/0], proyek Penjualan Korporat Wilayah Jabar 2026", "expect": {"kind": "confirm", "rows": [{"nama_karyawan": "Eka Mulyani", "nama_proyek": "Penjualan Korporat Wilayah Jabar 2026", "tanggal": "2026-09-29", "jenis_pekerjaan": "bikin laporan penjualan", "jam_mulai": "09:00", "jam_selesai": "11:00", "keterangan": "[2/1/1/0]"}]}}, {"user": "ya", "expect": {"kind": "call", "calls": [{"nama_karyawan": "Eka Mulyani", "nama_proyek": "Penjualan Korporat Wilayah Jabar 2026", "tanggal": "2026-09-29", "jenis_pekerjaan": "bikin laporan penjualan", "jam_mulai": "09:00", "jam_selesai": "11:00", "keterangan": "[2/1/1/0]"}]}}], "notes": "Spec rule 2 with a label word other than 'review': 'hasil' puts the bracket in keterangan, copied verbatim (2 > 1 is valid, never clamped) and no status word is added. Kemarin = 2026-09-29, inside the 3-day window."}
```

Also sweep: `Select-String -Path eval\cases.jsonl -Pattern "tim_pekerjaan|\"review\":"`
must return NO matches after the transforms (the word "review" inside user
messages and category names stays — only the key and stale notes go).

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -q`
Expected: ALL test_eval tests pass (parse, score, dataset, fixture checks).

Test command for task-done: `.venv\Scripts\python.exe -m pytest tests/test_eval.py`

---

## Task 6: stale `test_agent.py` cleanup (rename + deleted-field removal)

**Files:** `tests/test_agent.py` only — no `src/` changes.

RED first: run `.venv\Scripts\python.exe -m pytest tests/test_agent.py -q`
Expected: 13 failures (the baseline list below) — watch them fail.

Then apply exactly these edits:

1. `ROW2_ARGUMENTS` (line ~150): `"review":"[1/1/0/2] Done"` →
   `"keterangan":"[1/1/0/2] Done"`.
2. Line ~192: `rows[1]["review"]` → `rows[1]["keterangan"]`.
3. `test_null_optional_fields_are_accepted_and_stripped`: delete
   `args["tim_pekerjaan"] = None` and `assert "tim_pekerjaan" not in final`;
   `args["review"]` → `args["keterangan"]`; `assert "review" not in final` →
   `assert "keterangan" not in final`.
4. `test_no_close_candidate_ends_in_model_question` expected tool content →
   `'"zzz qqq" not found in the project list. Ask the user to write the full name or check the spelling.'`
5. DELETE the `with_tim` helper and the three tests
   `test_unknown_tim_member_redirects_to_find_employee`,
   `test_unknown_tim_member_blocks_whole_batch`,
   `test_valid_tim_member_passes_through` (they cover a field the user deleted).
   Update the section comment
   `# --- membership checks: fail-closed lists, tim_pekerjaan, canonical rewrite ---`
   → `# --- membership checks: fail-closed lists, canonical rewrite ---`.
6. `test_case_mismatch_rewritten_to_canonical`: delete
   `row["tim_pekerjaan"] = "budi santoso, IMAM IHSANI"` and
   `assert args["tim_pekerjaan"] == "Budi Santoso, Imam Ihsani"` (keep the
   nama_karyawan/nama_proyek canonical asserts — still valid coverage).
7. `DRIFTED_ROW2_ARGUMENTS` (line ~709): `"review"` key → `"keterangan"`.
8. `test_confirmed_rows_parses_last_assistant_summary` expected row 2 key
   `"review"` → `"keterangan"` (value unchanged).
9. `test_row_guard_null_optionals_match_summary_without_keys`: delete
   `args["tim_pekerjaan"] = None` and `assert "tim_pekerjaan" not in final`;
   `review` → `keterangan` in the remaining arg and assert.
10. `test_resolve_name_not_found` expected →
    `'"zzz qqq" not found in the project list. Ask the user to write the full name or check the spelling.'`

Sweep: `Select-String -Path tests\test_agent.py -Pattern "review|tim_pekerjaan"`
→ only intentional leftovers: none expected (the string `[1/1/0/2] Done`
values are fine — they are slot VALUES, not keys).

Run: `.venv\Scripts\python.exe -m pytest tests/test_agent.py -q`
Expected: ALL pass.

Test command for task-done: `.venv\Scripts\python.exe -m pytest tests/test_agent.py`

---

## Task 7: `test_main_chat` fixture + full green suite

**Files:** `tests/test_main_chat.py`

RED first: `.venv\Scripts\python.exe -m pytest tests/test_main_chat.py -q`
Expected: 3 errors — `main has no attribute 'get_employees'`.

Edit: in the `client` fixture DELETE the line
`monkeypatch.setattr(main, "get_employees", lambda: [])` (main.py has no such
function — the patch itself is the bug). Touch nothing else.

Run: `.venv\Scripts\python.exe -m pytest tests/test_main_chat.py -q`
Expected: all pass. If a deeper failure appears, debug it (it cannot be this
patch line — main has no `get_employees` at all); if it turns out to be a
behavior question beyond stale cleanup, stop and report it instead of
inventing behavior.

Then the milestone — full suite:
`.venv\Scripts\python.exe -m pytest -q`
Expected: `all passed` / 0 failed, 0 errors (baseline was 24F+3E).

Test command for task-done: `.venv\Scripts\python.exe -m pytest`

---

## Task 8: PRD/FRD dated decision note

**Files:** `PRD_FRD_create_alokasi_agent.md`

No behavior change. Steps:

1. Read the decision-note list near line 179 (the 2026-10-12 note). Append
   AFTER it, same bullet style:

```markdown
- **Decision (2026-10-30):** the optional tool field is `keterangan` (renamed from `review`) so the key matches the CI3 column — `main.py` forwards each row verbatim to `createAlokasi`, so any other key would silently drop the value. A status bracket `[a/b/c/d]` is copied exactly as typed: never recalculated, never corrected, never given "Done"/"not done", and the numbers never decide where it goes. Placement is decided only by position, label word, or asking: written together with the task name -> it stays in `jenis_pekerjaan` verbatim; beside a label word (review/hasil/keterangan) -> `keterangan`; bare or unclear (including "review" read as part of the task name) -> one short Indonesian question "Itu untuk jenis pekerjaan atau keterangan?" before anything is sent. The 3-day entry window is unchanged (user-facing notice: "Keterangan hanya bisa diisi maksimal 3 hari setelah tanggal tugas."). `update_alokasi` remains blocked on the three CI3 items: a RecID update endpoint, a per-employee-per-date list endpoint, and the confirmed `keterangan` column on `createAlokasi`.
```

2. Sanity sweep: `Select-String -Path PRD_FRD_create_alokasi_agent.md -Pattern "review"`
   → only the label-word mentions in the new note are allowed; the PRD's
   existing samples already use `keterangan` (they need no change).

Test command for task-done: `.venv\Scripts\python.exe -m pytest`
(Expected: still fully green — Task 8 touches docs only.)

---

## Review Focus (for the final whole-branch reviewer)

- Live model behavior is NOT covered by unit tests; it lives only in
  `eval/cases.jsonl` and needs `OPENAI_API_KEY` to run (`scripts/run_eval.py`).
  Cases 002/003 (strip user-typed "done"), 006/007 (ask instead of guess),
  008 (glued bracket), 009 (`hasil` label) are the new judgment calls.
- `_SUMMARY_OPTIONAL` is now a 1-tuple: check `parse_summary` handles 6-part
  lines and still rejects >6 parts.
- Blank/null optionals: validator accepts both, agent strips both — the
  backend must never receive `keterangan: ""`.
- No commits were made; `main.py` is untouched; `tim_pekerjaan` remains
  deleted in `src/` (tests/eval now agree).
- Rulings made during execution are in the workspace ledger
  (`.superpowers/sdd/2026-10-30-keterangan-bracket-rules/progress.md`).
