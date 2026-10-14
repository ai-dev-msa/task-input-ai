# Design: list membership checks for nama_karyawan, nama_proyek, tim_pekerjaan

- Date: 2026-10-14
- Status: approved by the user (design sections 1-2 in session).
- Scope: AI track only (`src/alokasi_agent/agent.py`, `tests/test_agent.py`).

## Problem

The code gate for `nama_karyawan` and `nama_proyek` (`_employee_problem`,
`_project_problem`) has three leaks, and `tim_pekerjaan` has no code check at
all (prompt rule only):

1. **Fail-open:** an empty `employees`/`projects` list skips the check
   entirely, so an off-list name goes straight to the ERP.
2. **Non-canonical pass-through:** the check accepts
   `value.strip().casefold()`, but the envelope sends the model's original
   string, so `"oprS Divisi win 2026"` is written unregistered-exact.
3. **`tim_pekerjaan`:** unregistered team members pass freely.

## Decisions

### Check order on a `create_alokasi` call

1. FR-05 format validation (unchanged, retry-once stays).
2. **Fail-closed:** `employees` or `projects` empty -> error envelope
   (`success:false`, `type:"error"`, empty `function_name`/`arguments`,
   reply and history reason):
   - `Daftar karyawan tidak tersedia, coba lagi.`
   - `Daftar proyek tidak tersedia, coba lagi.`
   - `Daftar karyawan dan proyek tidak tersedia, coba lagi.`
   Nothing reaches the ERP. Plain-text model replies pass through untouched.
3. `nama_karyawan` membership -> `nama_proyek` membership -> each
   `tim_pekerjaan` member (employees guaranteed non-empty by step 2).

### Message formats

Existing employee/project wording stays byte-identical (current tests keep
passing). Multiple problems join with a space. No function_call goes out
while any problem exists.

| case | nama_karyawan / nama_proyek (unchanged) | tim_pekerjaan (new) |
|---|---|---|
| 1 close match | `Maksud kamu "Y"?` | `Maksud kamu "Y" untuk tim, atau hapus "X"?` |
| several | `Karyawan "X" tidak ada. Pilih: A, B` | `Anggota tim "X" tidak ada. Pilih: A, B, atau hapus "X"?` |
| none | `Karyawan "X" tidak ada di daftar karyawan.` | `Anggota tim "X" tidak ada di daftar karyawan. Hapus dari tim?` |

The no-match template reads `tidak ada di daftar karyawan` for both the
employee and tim kinds (tim members are employees) and
`tidak ada di daftar proyek` for the project kind.

If the user answers "hapus", the code question sits in history and the model
re-offers the row without that member -- no prompt edit needed
(`tim_pekerjaan` is already omit-when-absent).

### Canonical rewrite

When every check passes, accepted values are replaced with the exact list
entry: `nama_karyawan`, `nama_proyek`, and each `tim_pekerjaan` member
(re-joined with `", "`). The row's JSON is re-serialized
(`separators=(",", ":")`) **only if a value actually changed**, so untouched
rows keep the model's exact argument string.

### Implementation shape

All in `src/alokasi_agent/agent.py`, plain functions, no new files:

- `_list_problem(values, valid, kind, *, offer_delete=False) -> str | None`:
  trim/casefold canonical map (first spelling wins), difflib
  `get_close_matches(n=3, cutoff=0.5)`, templates above.
- `_employee_problem` / `_project_problem` become thin call sites;
  `_tim_problem(args, employees)` splits `tim_pekerjaan` on `","` (strip,
  drop empty segments).
- Canonical lookup helper used at rewrite time.
- Fail-closed guard before the three checks, reusing the existing
  error-envelope shape.

## Verification

- New tests in `tests/test_agent.py`:
  - tim off-list x3 (close / several / none) -> wording per the table,
    `type == "text"`.
  - case-mismatched employee, project, and tim member -> accepted, envelope
    `arguments` rewritten to canonical spellings.
  - exact-match row -> `arguments` byte-identical to the model's raw string.
  - empty `employees` / empty `projects` / both -> error envelope naming the
    missing list.
- Existing tests stay green (`test_agent.py` raw-string, project question
  tests; all of `test_prompt.py`). Two tests pinned the old fail-open
  behavior and were rewritten to pin the new one:
  `test_empty_projects_list_skips_check` ->
  `test_empty_projects_list_blocks_call`, `test_empty_employees_list_skips_check`
  -> `test_empty_employees_list_blocks_call`.
- `.venv\Scripts\python.exe -m pytest`.

## Out of scope

- `src/alokasi_agent/prompt.py` (no prompt edits), `main.py` list sourcing,
  `src/alokasi_agent/schema.py` (FR-05 stays format-only), CI3 backend.
