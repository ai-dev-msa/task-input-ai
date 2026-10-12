# Optional `jam_selesai` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `jam_selesai` optional in the `create_alokasi` contract — on first insert the key is simply omitted when the user gives no end time; validation and the summary line cope with its absence.

**Architecture:** Pure contract change, no new modules. `jam_selesai` moves from `REQUIRED_FIELDS` to `OPTIONAL_FIELDS` in the shared schema (prompt, validator, tests all read it); the prompt stops asking for a missing end time (still asks when the user *tried* to give one and it is ambiguous/invalid); the eval summary parser accepts a bare `HH:MM` in the time slot. `keterangan` is untouched (CI3-side only). Update-after-insert stays backend-owned.

**Tech Stack:** Python stdlib only, pytest, existing `scripts/update_golden.py`.

## Global Constraints

- Tests: `.venv\Scripts\python.exe -m pytest`
- No commits unless the user explicitly asks (AGENTS.md).
- Empty-string `jam_selesai` (`""` / whitespace) is rejected — omit the key, same rule as `review`/`tim_pekerjaan`.
- `jam_mulai` stays required; when `jam_selesai` is present it must still be `HH:MM` and `> jam_mulai`.
- Golden snapshot must be regenerated, not hand-edited (`scripts/update_golden.py`).
- `seeds.txt` is frozen (FR-13 design) — only `eval/cases.jsonl` changes.

---

### Task 1: Schema — `jam_selesai` optional

**Files:**
- Modify: `src/alokasi_agent/schema.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_agent.py:282`
- Regenerate: `tests/golden/create_alokasi_input_schema.json`

**Interfaces:**
- Produces: `REQUIRED_FIELDS` = 5 names; `OPTIONAL_FIELDS` = `("jam_selesai", "review", "tim_pekerjaan")`; `validate_arguments()` accepts payloads without `jam_selesai`.

- [ ] **Step 1: Update the failing schema tests**

In `tests/test_schema.py`:
- Rename `SIX_FIELDS` → `REQUIRED` containing `{"nama_karyawan", "nama_proyek", "tanggal", "jenis_pekerjaan", "jam_mulai"}`; update `test_all_six_fields_are_required` to `test_required_fields_exclude_jam_selesai`:

```python
def test_required_fields_exclude_jam_selesai():
    schema = CREATE_ALOKASI_TOOL["input_schema"]
    assert set(schema["required"]) == REQUIRED
    assert len(schema["required"]) == 5
```

- Remove this parametrized rejection case (line 88 — it is now valid):

```python
json.dumps({k: v for k, v in VALID_ARGS.items() if k != "jam_selesai"}),
```

- Add acceptance + blank-rejection tests:

```python
def test_validate_accepts_missing_jam_selesai():
    payload = json.dumps({k: v for k, v in VALID_ARGS.items() if k != "jam_selesai"})
    assert validate_arguments(payload) == []


@pytest.mark.parametrize("value", ["", "   "])
def test_validate_rejects_blank_jam_selesai(value):
    assert validate_arguments(as_json(jam_selesai=value)) != []
```

- Add `as_json(jam_selesai="")` to the blank-optional parametrize at line 77 (or covered by the test above — either is fine, prefer the explicit test).
- Fix `test_validate_reports_every_missing_field` (line 109): drop `"jam_selesai"` from the tuple.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_schema.py -v`
Expected: FAIL — `test_required_fields_exclude_jam_selesai` (required still has 6), `test_validate_accepts_missing_jam_selesai`, blank-jam_selesai test.

- [ ] **Step 3: Implement in `src/alokasi_agent/schema.py`**

```python
REQUIRED_FIELDS = (
    "nama_karyawan",
    "nama_proyek",
    "tanggal",
    "jenis_pekerjaan",
    "jam_mulai",
)

# Optional fields the model may add; absent means "user did not provide".
# jam_selesai: omit on insert when the user gives no end time (2026-10-12).
OPTIONAL_FIELDS = (
    "jam_selesai",
    "review",
    "tim_pekerjaan",
)
```

Update `CREATE_ALOKASI_DESCRIPTION`:

```python
CREATE_ALOKASI_DESCRIPTION = (
    "Buat satu baris alokasi kerja karyawan untuk satu tanggal: "
    "nama karyawan, nama proyek, tanggal, jenis pekerjaan, dan jam mulai; "
    "jam selesai opsional (kosongkan jika user tidak menyebutnya)."
)
```

No change needed in `validate_arguments` body: the required loop iterates `REQUIRED_FIELDS`, the optional loop already rejects blank values when the key is present, the time-format check already guards on non-empty, and the order check already requires both times. Update the module docstring line mentioning FR-01 if desired.

- [ ] **Step 4: Fix the agent retry-content assert**

In `tests/test_agent.py:282`, `INVALID_ARGUMENTS = '{"tanggal":"2026-13-45"}'` no longer produces a `jam_selesai` error. Change:

```python
assert "jam_selesai" in sent[-1]["content"]
```
to:
```python
assert "jam_mulai" in sent[-1]["content"]
```

- [ ] **Step 5: Regenerate golden and run the suite**

Run: `.venv\Scripts\python.exe scripts\update_golden.py` then `.venv\Scripts\python.exe -m pytest tests/test_schema.py tests/test_agent.py -v`
Expected: PASS (golden `required` list drops `jam_selesai`).

---

### Task 2: Prompt — stop asking for a missing end time

**Files:**
- Modify: `src/alokasi_agent/prompt.py`
- Modify: `tests/test_prompt.py`

**Interfaces:**
- Consumes: schema's optional `jam_selesai` (Task 1).
- Produces: prompt markers `"Plus three optional fields"`, `"omit jam_selesai"` pinned by tests.

- [ ] **Step 1: Update failing prompt markers**

In `tests/test_prompt.py::test_optional_field_rules_present` change line 82:

```python
assert "Plus three optional fields" in out
```

Add to `test_rule_markers_present` (or the optional-fields test):

```python
assert "omit jam_selesai" in out
assert "The function requires every field except jam_selesai" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompt.py -v` — Expected: FAIL on the new/changed markers.

- [ ] **Step 3: Edit `PROMPT_TEMPLATE`**

Instruction #1 (lines 52–60) — restructure:

```
1. Extract these five required fields from the message:
   - nama_karyawan: the person who will do the work (the assignee)
   - nama_proyek: the project
   - tanggal: the work date
   - jenis_pekerjaan: what the work is
   - jam_mulai: start time
   Plus three optional fields — include them only when the user gives them:
   - jam_selesai: the end time, only when the user gives an end time or a duration
   - review: the status/progress note for the task
   - tim_pekerjaan: the team members on this row
```

Instruction #3 summary format (line 64) — change the format line to:

```
   nama_karyawan | nama_proyek | tanggal | jenis_pekerjaan | jam_mulai-jam_selesai. Benar?
```
…and insert after it:
```
   When jam_selesai is not known, show only jam_mulai in that slot (no dash):
   nama_karyawan | nama_proyek | tanggal | jenis_pekerjaan | jam_mulai. Benar?
```

Field rules `jam_mulai / jam_selesai` (around lines 102–114) — replace the last two bullets:

```
- If the user gives an end time or a duration, resolve it. jam_selesai must
  be later than jam_mulai; if it isn't, or the end is ambiguous (a bare 6 or
  7), ask.
- If the user gives no end time and no duration, omit jam_selesai entirely:
  do not ask, do not guess a length, and do not send an empty value.
```

Validation checklist #4 (line 147):

```
4. jam_mulai matches HH:MM (24h). When jam_selesai is present it matches
   HH:MM and is after jam_mulai.
```

Checklist #7 (lines 153–155):

```
7. No argument is null, empty, or a placeholder such as "-", "N/A", or
   "tidak disebutkan". The function requires every field except jam_selesai:
   a missing required value means ask, not call. jam_selesai may be omitted;
   never send it empty.
```

Add one example after the existing "besok aku ngerjain modul PPN" example:

```
User: "besok aku nulis draft SOP pengadaan mulai jam 1 siang, proyek
   Penyusunan SOP Perusahaan 2026"
-> (logged-in user) | Penyusunan SOP Perusahaan 2026 | (besok) | nulis
   draft SOP pengadaan | 13:00. Benar?
   (No end time given: jam_selesai is omitted, not asked.)
```

- [ ] **Step 4: Run prompt tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompt.py -v` — Expected: PASS.

---

### Task 3: Eval parser — accept a bare `HH:MM` summary slot

**Files:**
- Modify: `src/alokasi_agent/eval.py:31,80-93`
- Modify: `tests/test_eval.py`

**Interfaces:**
- Consumes: Task 2's bare-`jam_mulai` summary format.
- Produces: `parse_summary()` returns rows without a `jam_selesai` key when the time slot is a single `HH:MM`.

- [ ] **Step 1: Add failing parser tests**

In `tests/test_eval.py` after the parse_summary tests:

```python
def test_parse_summary_single_time_has_no_jam_selesai():
    line = (
        "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN "
        "| 09:00. Benar?"
    )
    rows = parse_summary(line)
    assert rows == [
        {
            "nama_karyawan": "Imam Ihsani",
            "nama_proyek": "OPRS Divisi WIN 2026",
            "tanggal": "2026-09-29",
            "jenis_pekerjaan": "Development Modul PPN",
            "jam_mulai": "09:00",
        }
    ]
    assert "jam_selesai" not in rows[0]


def test_parse_summary_bad_single_time_returns_nothing():
    line = (
        "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN "
        "| 9:00. Benar?"
    )
    assert parse_summary(line) == []
```

- [ ] **Step 2: Verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -k parse_summary -v` — Expected: FAIL (range regex rejects `09:00`).

- [ ] **Step 3: Implement**

In `eval.py` line 31:

```python
_TIME_RANGE = re.compile(r"^\d{2}:\d{2}(-\d{2}:\d{2})?$")
```

Replace lines 85–93:

```python
        if "-" in jam:
            mulai, selesai = jam.split("-")
            row = {
                "nama_karyawan": nama,
                "nama_proyek": proyek,
                "tanggal": tanggal,
                "jenis_pekerjaan": jenis,
                "jam_mulai": mulai,
                "jam_selesai": selesai,
            }
        else:
            row = {
                "nama_karyawan": nama,
                "nama_proyek": proyek,
                "tanggal": tanggal,
                "jenis_pekerjaan": jenis,
                "jam_mulai": jam,
            }
```

Update the `parse_summary` docstring's format line to mention both shapes.

- [ ] **Step 4: Run eval tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -v` — Expected: PASS. (Field scoring needs no change: the key-union loop already treats a phantom `jam_selesai` as a miss and an absent-and-absent as not counted.)

---

### Task 4: Eval cases — two `missing_field` expectations flip

**Files:**
- Modify: `eval/cases.jsonl` (NOT `seeds.txt`)

- [ ] **Step 1: Rewrite `missing-003`**

User message unchanged (`"besok aku rapat evaluasi mingguan, proyek Pengembangan Produk Baru 2026"`). Expectation becomes ask-for-start-only; update notes:

```json
{"kind":"ask","asks_about":["jam_mulai"]}
```
Notes: `"jam_mulai is still required, jam_selesai is not. The agent asks for the start time only and must not use default working hours (08:30-17:30). Single turn: no confirm and no call."`

- [ ] **Step 2: Rewrite `missing-005` as a confirm+call without end time**

```json
{"id":"missing-005","category":"missing_field","difficulty":"medium","split":"dev","fixture":"v1","source":"written","now":"2026-09-30T14:05:00+07:00","user_name":"Raden Mahesa","turns":[{"user":"besok aku nulis draft SOP pengadaan mulai jam 1 siang, proyek Penyusunan SOP Perusahaan 2026","expect":{"kind":"confirm","rows":[{"nama_karyawan":"Raden Mahesa","nama_proyek":"Penyusunan SOP Perusahaan 2026","tanggal":"2026-10-01","jenis_pekerjaan":"nulis draft SOP pengadaan","jam_mulai":"13:00"}]}},{"user":"ya","expect":{"kind":"call","calls":[{"nama_karyawan":"Raden Mahesa","nama_proyek":"Penyusunan SOP Perusahaan 2026","tanggal":"2026-10-01","jenis_pekerjaan":"nulis draft SOP pengadaan","jam_mulai":"13:00"}]}}],"notes":"Start given (13:00), no end time and no duration: jam_selesai is optional now, so the agent confirms and calls without it. It must not ask and must not guess a typical length."}
```

- [ ] **Step 3: Verify untouched cases still parse and stay consistent**

Run: `.venv\Scripts\python.exe -m pytest tests/test_eval.py -v` (loader tests catch bad JSON). Confirm by eye that `timefmt-006` (ambiguous bare-7 end) and `invtime-002` (overnight) still expect `ask` — those are attempted-but-unusable end times, not absence.

---

### Task 5: Docs — PRD/FRD and integration guide

**Files:**
- Modify: `PRD_FRD_create_alokasi_agent.md`
- Check: `docs/integration-guide.md` (update only if it lists required args)

- [ ] **Step 1: §8.2 arguments table** — mark the row:

```
| `jam_selesai` | `HH:MM` | `12:00` | opsional (2026-10-12) |
```

- [ ] **Step 2: FR-01** — change "6 arguments" wording to: five required (`nama_karyawan`, `nama_proyek`, `tanggal`, `jenis_pekerjaan`, `jam_mulai`) plus optional `jam_selesai` (HH:MM; key omitted when the user gives no end time). Add a dated decision note: *"Decision (2026-10-12): jam_selesai is optional on insert — first insert may omit it; updating it later is backend/CI3-owned, not an AI-track tool. keterangan stays CI3-side."*

- [ ] **Step 3: FR-05** — note the order rule `jam_selesai > jam_mulai` applies only when `jam_selesai` is present (validator already behaved this way).

- [ ] **Step 4: FR-07** — adjust the example sentence so "Jam selesainya jam berapa?" is clearly for *ambiguous/invalid* end times, not for a missing one.

- [ ] **Step 5: integration-guide** — grep for a required-fields list; if the sample payloads are the only mention, leave the file alone.

---

### Task 6: Full verification

- [ ] **Step 1:** Run `.venv\Scripts\python.exe -m pytest` — all green.
- [ ] **Step 2 (optional, needs OPENAI_API_KEY):** `.venv\Scripts\python.exe scripts\smoke_agent.py` — sanity check that a live call still works with the new prompt.
