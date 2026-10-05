# PRD & FRD: Natural-Language Allocation Agent (`create_alokasi`)

> This document covers the **AI part only**. The backend (CI3) is built in parallel by a separate track.
> Items marked **TBD (not provided)** haven't been decided yet, so they're left open on purpose.

---

# Part 1: PRD (Product Requirements Document)

## 1. Problem Statement
We want to make it easier for employees to enter the tasks they plan to do each day and the results of their work. The same tool should also make it easier to delegate tasks to the team.

## 2. Target Users
MSA employees.

## 3. Goals
1. Extract information precisely and accurately.
2. Keep latency low.
3. Never make up crucial data such as IDs, names, and project names.
4. Enter crucial data correctly, based on what's in the database.

Numeric targets for accuracy and latency: **TBD (not provided)**.

## 4. Scope
- **In scope:** text input only. The LLM's only job is to turn unstructured information into structured information.
- **Out of scope:** any input other than text, and any role for the LLM beyond that translation.

## 5. Timeline, Owner, Dependencies
| Item | Detail |
|---|---|
| Timeline | 7 days (30/9 - 7/10) |
| Owner | IT MSA |
| Dependencies | None |
| Parallel work | Backend and AI run in parallel; this document covers the AI part only |

## 6. Product Description
The agent reads a natural-language message in Indonesian and converts it into a `create_alokasi` function call, and returns that call (or a clarification question) to the caller. Sending the call to CI3, which creates the allocation record, is the backend's job — the AI track does not contact CI3 (boundary decision, 2026-09-30).

**Example input (`raw_message`):**
> Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026

**Example output (`arguments`):**
```json
{
  "nama_karyawan": "Imam Ihsani",
  "nama_proyek": "OPRS Divisi WIN 2026",
  "tanggal": "2026-09-29",
  "jenis_pekerjaan": "Development Modul PPN",
  "jam_mulai": "09:00",
  "jam_selesai": "12:00"
}
```

## 7. Design Decision: Output as Function Call
The agent's job is to take an action (write a row to the database), not to write text for a person to read. Since the output goes straight into CI3, it needs to be a machine-readable function call.
- The tool definition (name, argument types, required fields) keeps the output structure consistent.
- One contract is shared by the prompt, the validator, and the tests.
- Routing is simple: the model either calls the function or replies with text, such as a clarification question.
- It's easy to extend later with functions like `update_alokasi`, `delete_alokasi`, or `cek_alokasi`.
- The LLM only proposes the call; the model confirms with the user before proposing it. Our code validates it; the backend owns the actual run against CI3.
- Trade-off: it takes more setup than plain JSON output, and we still need validation in code, because the model can return well-formed but wrong values.

---

# Part 2: FRD (Functional Requirements Document)

## 8. Tool Contract

### 8.1 Function
`create_alokasi`

### 8.2 Arguments
| Argument | Format | Example |
|---|---|---|
| `nama_karyawan` | string | `Imam Ihsani` |
| `nama_proyek` | string | `OPRS Divisi WIN 2026` |
| `tanggal` | `YYYY-MM-DD` | `2026-09-29` |
| `jenis_pekerjaan` | string | `Development Modul PPN` |
| `jam_mulai` | `HH:MM` | `09:00` |
| `jam_selesai` | `HH:MM` | `12:00` |

Which arguments are required is defined in FR-01.

### 8.3 Response Envelope
The AI track returns all fields **except** `hasil_ci3` (boundary decision, 2026-09-30).

| Field | Description |
|---|---|
| `success` | boolean |
| `type` | e.g. `function_call` |
| `function_name` | e.g. `create_alokasi` |
| `arguments` | JSON string of the six arguments |
| `hasil_ci3` | response from CI3 (see 8.4) — **backend-owned, added by the backend track, not part of the AI response** |
| `raw_message` | original user message |
| `user_id` | present in the envelope (`null` in the sample) |
| `reply` | model's text reply — confirmation summary or clarification question (`null` on a tool call) — added 2026-10-01, FR-04 |
| `history` | conversation turns after this reply — store it and send it back with the next message (FR-16) |

### 8.4 `hasil_ci3` Structure (from sample) — backend-owned reference

> This structure belongs to the CI3 backend codebase. The AI track must not model or validate it (boundary decision, 2026-09-30); it is documented here as reference only.
| Field | Sample value |
|---|---|
| `success` | `true` |
| `type` | `created` |
| `message` | `Alokasi berhasil dibuat` |
| `database` | `TESTING - 192.168.1.94` |
| `data.Cabang` | `WIN - Pusat` |
| `data.Jenis Alokasi` | `Manpower` |
| `data.Jenis Pekerjaan` | `Development Modul PPN` |
| `data.Jenis Proyek` | `OPRS` |
| `data.Kode Proyek` | `26.01.000.00.0102.0002` |
| `data.Nama Alokasi` | `Imam Ihsani` |
| `data.Nama Proyek` | `OPRS Divisi WIN 2026` |
| `data.RecID` | `10089283` |
| `data.Tanggal` | `2026-09-29` |
| `data.bagian` | `System` |
| `data.jam_mulai` | `09:00` |
| `data.jam_selesai` | `12:00` |
| `data.keterangan` | `null` |
| `data.ketercapaian` | `null` |
| `data.kode_karyawan` | `WIN.01.2023.18` |
| `data.persentase_hasil` | `null` |
| `data.tanggal_input` | `2026-09-29 16:37:41` |

### 8.5 Full Sample Envelope
```json
{
  "arguments": "{\"nama_karyawan\":\"Imam Ihsani\",\"nama_proyek\":\"OPRS Divisi WIN 2026\",\"tanggal\":\"2026-09-29\",\"jenis_pekerjaan\":\"Development Modul PPN\",\"jam_mulai\":\"09:00\",\"jam_selesai\":\"12:00\"}",
  "function_name": "create_alokasi",
  "hasil_ci3": {
    "data": {
      "Cabang": "WIN - Pusat",
      "Jenis Alokasi": "Manpower",
      "Jenis Pekerjaan": "Development Modul PPN",
      "Jenis Proyek": "OPRS",
      "Kode Proyek": "26.01.000.00.0102.0002",
      "Nama Alokasi": "Imam Ihsani",
      "Nama Proyek": "OPRS Divisi WIN 2026",
      "RecID": 10089283,
      "Tanggal": "2026-09-29",
      "bagian": "System",
      "jam_mulai": "09:00",
      "jam_selesai": "12:00",
      "keterangan": null,
      "ketercapaian": null,
      "kode_karyawan": "WIN.01.2023.18",
      "persentase_hasil": null,
      "tanggal_input": "2026-09-29 16:37:41"
    },
    "database": "TESTING - 192.168.1.94",
    "message": "Alokasi berhasil dibuat",
    "success": true,
    "type": "created"
  },
  "raw_message": "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026",
  "history": [
    {
      "role": "user",
      "content": "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026"
    },
    {"role": "assistant", "content": ""}
  ],
  "success": true,
  "type": "function_call",
  "user_id": null
}
```

## 9. Functional Requirements

FR-01 to FR-16 map to workflow issues #1 to #16.

### Milestone 1: Foundation

#### FR-01 (#1): Define the tool schema and contract
- Write the `create_alokasi` tool definition with 6 arguments: `nama_karyawan`, `nama_proyek`, `tanggal` (YYYY-MM-DD), `jenis_pekerjaan`, `jam_mulai`, and `jam_selesai` (HH:MM).
- Mark which fields are required.
- Document the response envelope: `success`, `type`, `function_name`, `arguments`, `hasil_ci3`, and `raw_message`.
- **Done when:** the schema lives in a single file that the prompt, the validator, and the tests all share.

#### FR-02 (#2): Set up the LLM client and base system prompt
- Add the LLM client with settings for model, temperature, and timeout.
- Write a system prompt that covers the role, tool-use rules, and "never guess missing fields".
- Inject the current date and timezone (WIB) into the prompt.
- **Done when:** a simple prompt returns a `create_alokasi` tool call.
> **System prompt delivered (Slice B, 2026-10-01).** `src/alokasi_agent/prompt.py` (`PROMPT_TEMPLATE` + `build_system_prompt(now, user_name, employees, projects)`). **Injected-context contract:** the caller supplies `user_name`, `employee_list`, `project_list` per request — this repo performs no DB lookups (boundary §6); WIB time is derived from `now`, rendered `Rabu, 30 September 2026, 14:05 WIB`. Done-condition: `scripts/smoke_llm.py` live run returns a tool call.

#### FR-03 (#3): Build the CI3 API client
> **Owner: backend (CI3) track — out of AI scope (boundary decision, 2026-09-30).** Kept here for the backend team's reference.

- Add a wrapper for the CI3 endpoint with auth, timeout, and error mapping.
- Provide a mock/stub mode for local development, and keep the TESTING DB separate from production through config.
- **Done when:** `create_alokasi` can be called against both the mock and the TESTING DB.

### Milestone 2: Core extraction

#### FR-04 (#4): First-pass extraction (happy path)
- Take `raw_message`, run it through the LLM, and get the tool-call arguments.
- Return the response envelope.
- **Done when:** the example message produces exactly the sample `arguments`.
> **Delivered (2026-10-01).** `src/alokasi_agent/agent.py` — `run(raw_message, *, user_name, employees, projects, history, user_id, now, client) -> (envelope, history)`. Routes tool call vs text reply (`type`: `function_call` | `text`), carries the model's text in `reply`, threads conversation history across the confirmation loop. Done-condition: `scripts/smoke_agent.py` live run exits 0 with the sample arguments. Argument parsing/validation stays FR-05. History transport: FR-16.

#### FR-05 (#5): Structured output, validation, and retry/fallback
- Validate the arguments (Pydantic or JSON Schema): date format, HH:MM format, and `jam_selesai > jam_mulai`.
  - Real calendar/time validity (e.g. reject `2026-13-45`, `99:99`) is owned here: parse with `date.fromisoformat`, enforce hour ≤ 23 and minute ≤ 59. FR-01's patterns only check shape.
- If validation fails, retry once and pass the error message back to the LLM.
- If it still fails, return `success: false` with a clear reason instead of a partial call.
- **Done when:** malformed LLM output never reaches the backend.
> **Delivered (2026-10-01).** `src/alokasi_agent/schema.py` — `validate_arguments()` (stdlib `date.fromisoformat` for real calendar dates, hour ≤ 23 / minute ≤ 59, `jam_selesai > jam_mulai`, plus completeness and unknown-key checks). `src/alokasi_agent/agent.py` — `run()` retries once with the errors in `tool` messages; a second failure returns `success: false`, `type: "error"`, empty `arguments`, and the Indonesian reason in `reply`. Done-condition: `tests/test_agent.py::test_invalid_twice_returns_error_envelope`.

#### FR-06 (#6): Deterministic date/time normalizer
> **Absorbed into prompt rules (2026-10-01).** Date/time interpretation (relative phrases, "jam 09 pagi", ranges) lives in the FR-02 system prompt — no separate code normalizer; FR-05's validator still checks formats. The "unit tests cover Indonesian variants" done-condition below is superseded by these prompt rules.
> **Coverage gap-fill (2026-10-01).** Written-out dates ("29 September 2026" → `2026-09-29`), defaulting a missing year to the current year, `"09.00"` = `"09:00"`, and `"09:00-12:00"` ranges added to `PROMPT_TEMPLATE`; pinned by marker assertions in `tests/test_prompt.py::test_rule_markers_present`.
- Handle "29 September 2026", "besok", "lusa", "senin depan", and "kemarin".
- Handle "jam 09 pagi", "12 siang", "3 sore", "jam 8 malam", "09.00", and ranges like "09:00-12:00".
- Preferably let the LLM extract the raw strings and have code convert them, or double-check the LLM's values in code.
- **Done when:** unit tests cover the Indonesian variants, and the year defaults to the current year when it's left out.

### Milestone 3: Robustness

#### FR-07 (#7): Missing/ambiguous field handling (clarification loop)
- Detect missing required fields and ask a targeted follow-up question, e.g. "Jam selesainya jam berapa?".
- Merge the user's answer into the pending arguments (short conversation state).
- **Done when:** a partial message followed by an answer produces a complete call.
> **Delivered (2026-10-01).** No new `src/` code: detect-and-ask is prompt instruction #4 (marker pinned in `tests/test_prompt.py`), the short conversation state is FR-04 history threading, and FR-05 blocks any incomplete call (the model must ask instead). Done-condition: `tests/test_agent.py::test_partial_message_then_answer_produces_complete_call` (stubbed) and live `scripts/smoke_agent.py --partial` (interactive). History transport: FR-16.

#### FR-08 (#8): Edge-case input handling
> **Known gap (2026-10-01):** prompt allows several records in one confirmation, but `ResponseEnvelope.arguments` holds a single JSON object (FR-01) — multi-record needs an FR-08 decision (sequential calls vs. list payload). Non-blocking for Slice B.
> **Decision (2026-10-01): parallel calls per row.** On confirmation the model emits one `create_alokasi` tool call per row in the same reply; `run()` validates every call (retry once with per-call `tool` replies) and refuses if any row is still invalid. Single row keeps the object-string `arguments` (§8.5 sample unchanged); multiple rows return a JSON array string of row objects — the backend iterates the array. Prompt rules and the two-row example live in `src/alokasi_agent/prompt.py`; pinned by `tests/test_agent.py::test_multiple_rows_produce_array_arguments`.
- Cover typos in names, mixed Indonesian/English, and extra filler text.
- Cover multiple allocations in one message ("pagi dev PPN, siang testing") and non-allocation messages (out of scope).
- Define what happens with overnight or invalid time ranges.
- **Done when:** every case has a defined outcome: call, ask, split, or refuse.

#### FR-09 (#9): Entity resolution (employee and project names)
> **Absorbed into prompt rules (2026-10-05).** Matching is prompt-only: "Must match a valid employee exactly. Fix only obvious casing or typos when exactly one employee fits. If two or more could fit, or none fits, ask." (`src/alokasi_agent/prompt.py` field rules), with the multi-candidate example "Budi yang mana: Budi Santoso atau Budi Hartono?". The comparison runs only against the caller-injected `{{employee_list}}` / `{{project_list}}` — this repo does no DB retrieval (boundary §6), so "not found in CI3" and agent-vs-CI3 fuzzy matching stay backend questions (same owner as FR-03). Near-match suggestion ("Maksud kamu Imam Ihsani?") is left to the model's judgment; FR-10's confirmation shows the resolved name before any write. Pinned by marker assertions in `tests/test_prompt.py::test_rule_markers_present`.
- Handle a name not found in CI3, multiple matches, and near-matches ("Imam Ihsan").
- Decide where fuzzy matching lives (agent or CI3), and show the user the candidates when a name is ambiguous.
- **Done when:** the agent asks "Maksud kamu Imam Ihsani?" instead of failing silently or writing the wrong data.

#### FR-10 (#10): Confirmation step before write
> **Owner: AI track (flipped 2026-10-01).** The confirmation dialog is AI-side: the model shows the parsed summary and waits for "ya" before emitting the `create_alokasi` tool call (prompt rule in `src/alokasi_agent/prompt.py`). Inline edits ("ganti jam selesai jadi 13:00") stay AI-side — text → arguments, same as FR-07's merge logic. The backend still performs the actual write. History transport: FR-16.

- Show a parsed summary (name, project, date, time, task) and wait for "ya" or "batal" before calling CI3.
- Allow inline edits ("ganti jam selesai jadi 13:00") using the same merge logic as FR-07.
- **Done when:** nothing is written without confirmation (configurable).

#### FR-11 (#11): Backend error and duplicate handling
> **Owner: backend (CI3) track — out of AI scope (boundary decision, 2026-09-30).** The AI track never talks to CI3, so it never sees these errors.

- Handle CI3 failures (`success: false`, timeout, 5xx) and overlapping time slots for the same employee.
- Reply with friendly Indonesian messages.
- **Done when:** errors are mapped and logged, and never crash the agent.

#### FR-16 (#16): Carry chat history across turns
- Return the conversation so far in the response envelope as `history` (a list of `{role, content}` turns, including this reply).
- The caller stores it and passes it back with the next request; `run()`'s existing `history` kwarg is the input side (FR-04 already threads it in-process).
- Without it, a confirmation like "Benar" arrives with no context and the model cannot confirm the summary it showed one turn earlier.
- **Done when:** a two-turn conversation (summary, then "Benar") where turn 2 reuses turn 1's envelope `history` produces the `create_alokasi` call.

### Milestone 4: Quality and optimization

#### FR-12 (#12): Build the eval dataset
- Collect 40-60 Indonesian messages, each with its expected `arguments`.
- Cover the happy path, relative dates, missing fields, typos, out-of-scope messages, and multiple allocations.
- Store the dataset as JSONL in the repo.
- **Done when:** the dataset is versioned and every case is tagged by category.

#### FR-13 (#13): Regression test runner and metrics
- Run the eval on every prompt or model change, ideally in CI.
- Report field-level accuracy, exact-match rate, and clarification precision, plus a comparison with the previous run.
- **Done when:** a PR fails if accuracy drops below the threshold. (Threshold value: **TBD (not provided)**.)

#### FR-14 (#14): Prompt and token optimization
- Trim the system prompt, add few-shot examples only where the evals show failures, and compare model sizes for cost and latency.
- **Done when:** the eval score is the same or better at lower token usage and latency, and this is documented.

#### FR-15 (#15): Logging, observability, and audit trail
- Log `raw_message`, the extracted `arguments`, validation results, retries, and the CI3 response.
- Redact sensitive data if needed.
- **Done when:** any bad allocation can be traced back to the message that caused it.

## 10. Suggested Order
#1 → #2 → #3 → #4 → #5 → #6 → #12 (start the dataset early) → #7 → #8 → #9 → #10 → #11 → #13 → #14 → #15 → #16

## 11. GitHub Labels
`foundation`, `extraction`, `robustness`, `eval`, `optimization`

| Milestone | Issues | Label |
|---|---|---|
| Foundation | #1, #2, #3 | `foundation` |
| Core extraction | #4, #5, #6 | `extraction` |
| Robustness | #7, #8, #9, #10, #11, #16 | `robustness` |
| Quality and optimization | #12, #13 | `eval` |
| Quality and optimization | #14, #15 | `optimization` |

## 12. Open Items (Not Provided)
| Item | Status |
|---|---|
| Numeric target for extraction accuracy | TBD (not provided) |
| Numeric target for latency | TBD (not provided) |
| CI accuracy threshold (FR-13) | TBD (not provided) |
| Which arguments are required (FR-01) | TBD (not provided) |
| LLM provider/model | TBD (not provided) |
| Per-issue owners and day-by-day schedule within the 7 days | TBD (not provided) |
