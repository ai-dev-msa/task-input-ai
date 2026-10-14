# Multi-allocation row-loss fix (FR-08 confirmed-row guard) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** What gets inserted into the ERP is exactly what the user confirmed — the confirm turn's rows must match the confirmed summary row-for-row and field-for-field, or the agent nudges once and then refuses instead of writing a partial or altered batch.

**Architecture:** The confirmed summary text is the single source of truth. On the confirm turn, `run()` parses the last assistant summary back into structured rows (`parse_summary`, already in `src/alokasi_agent/eval.py`) and compares them with the model's emitted `create_alokasi` calls. Match → write as today. Mismatch (count or any field) → one corrective retry carrying the confirmed rows as JSON → still mismatched → error envelope, nothing written. Separately, `main.py` isolates each ERP POST so one failed row no longer hides the rows already written, and ERP errors return the *updated* `history`.

**Tech Stack:** Python 3.11+, pytest (stubbed LLM via existing `make_stub`), Flask test client for `main.py`. No new dependencies.

## Global Constraints

- AGENTS.md: simplest solution that works, plain functions, no classes/abstractions, minimal changes, do not refactor unrelated code.
- AGENTS.md: implement only this bug fix — no future FRs, leave PRD/FRD TBDs open.
- AGENTS.md: **do not commit** unless explicitly asked (no commit steps in this plan).
- Tests: `.venv\Scripts\python.exe -m pytest` (currently 123 passing).
- Live checks need `OPENAI_API_KEY` in `.env` (model `gpt-5.6-luna`).
- Comment only non-obvious things; existing code comments are EN/ID mixed.

## Root cause (why this plan exists)

The flow is: turn 1 extracts and shows the summary **as text** (`nama | proyek | tanggal | jenis | jam. Benar?`), turn 2 on "ya" the model **re-derives the rows from scratch** and emits the tool calls. The confirmed rows are never stored as structured data — only as display text in `history`. So "what was confirmed" and "what gets inserted" are two independent model outputs that nothing ever compares. Evidence: live repro was 12/12 clean in-process, so the model usually behaves — the code has no guard for when it doesn't. Silent loss paths found:

1. **FR-05 retry can shrink the batch** — `agent.py:157` only refuses when *errors* remain. 2 calls sent, one invalid, retry returns 1 valid call → errors clear → 1 row written though 2 were confirmed.
2. **No comparison against the confirmed summary** — on the "ya" turn nothing checks the emitted rows against the summary the user approved (count *or* field values — the model can also drift a time or drop a `review` and it would be written silently).
3. **`main.py` partial-write hazard** — POST #1 succeeds, POST #2 raises → outer `except` (`main.py:267`) returns a generic error echoing the *input* history (`main.py:279`), hiding that row 1 was committed and dropping the confirm turn from history.

**User decision (2026-10-14):** exact row equality — "confirm the row, then make sure the rows inserted match what was confirmed." Rejected alternative: emitting structured `tool_calls` with the turn-1 summary (breaks the edit flow — the server could not tell "updated rows for re-confirmation" from "confirmed, write them", and it would change the envelope/history contract the external frontend depends on).

---

### Task 1: Confirmed-row guard in `run()`

**Files:**
- Modify: `src/alokasi_agent/agent.py` (import + two helpers after `_employee_problem` ~line 103; decision chain lines 157-196)
- Test: `tests/test_agent.py` (append after the existing FR-08 section, i.e. after `test_multi_row_invalid_twice_returns_error_envelope`)

**Interfaces:**
- Consumes: existing `make_stub`, `tool_reply`, `tool_reply_multi`, `SAMPLE_ARGUMENTS`, `ROW2_ARGUMENTS`, `INVALID_ARGUMENTS`, `call_run` (tests/test_agent.py:23-57, 146-164, 257); `parse_summary` from `alokasi_agent.eval` (pure, no I/O at import — eval imports only `json`, `re`, `pathlib`).
- Produces: `_confirmed_rows(history: Sequence[dict]) -> list[dict[str, str]]` and `_same_rows(calls, confirmed) -> bool` in `alokasi_agent.agent`; `run()` may make a second corrective LLM call after the FR-05 retry. Refusal envelope shape unchanged (`success: False`, `type: "error"`, `arguments: ""`, `reply` = reason).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent.py`:

```python
# --- FR-08 row guard: what is inserted must equal what was confirmed ---

TWO_ROW_SUMMARY = (
    "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN"
    " | 09:00-12:00\n"
    "Budi Santoso | OPRS Divisi WIN 2026 | 2026-09-30 | Testing sistem"
    " | 16:30-17:00 | [1/1/0/2] Done. Benar?"
)
PENDING_HISTORY = [
    {"role": "user", "content": "pagi dev PPN, siang testing proyek OPRS"},
    {"role": "assistant", "content": TWO_ROW_SUMMARY},
]
# Same as ROW2_ARGUMENTS but jam_mulai drifted to 16:00 — valid JSON and
# valid format, so FR-05 never sees it; only the row guard can catch it.
DRIFTED_ROW2_ARGUMENTS = (
    '{"nama_karyawan":"Budi Santoso","nama_proyek":"OPRS Divisi WIN 2026",'
    '"tanggal":"2026-09-30","jenis_pekerjaan":"Testing sistem",'
    '"jam_mulai":"16:00","jam_selesai":"17:00","review":"[1/1/0/2] Done"}'
)


def test_confirmed_rows_parses_last_assistant_summary():
    from alokasi_agent.agent import _confirmed_rows

    rows = _confirmed_rows(PENDING_HISTORY)
    assert rows == [
        {
            "nama_karyawan": "Imam Ihsani",
            "nama_proyek": "OPRS Divisi WIN 2026",
            "tanggal": "2026-09-29",
            "jenis_pekerjaan": "Development Modul PPN",
            "jam_mulai": "09:00",
            "jam_selesai": "12:00",
        },
        {
            "nama_karyawan": "Budi Santoso",
            "nama_proyek": "OPRS Divisi WIN 2026",
            "tanggal": "2026-09-30",
            "jenis_pekerjaan": "Testing sistem",
            "jam_mulai": "16:30",
            "jam_selesai": "17:00",
            "review": "[1/1/0/2] Done",
        },
    ]
    assert _confirmed_rows([]) == []
    assert _confirmed_rows([{"role": "assistant", "content": "Untuk proyek apa?"}]) == []
    assert _confirmed_rows([{"role": "user", "content": "a | b | c | d | e"}]) == []


def test_row_guard_matching_rows_pass_without_nudge():
    calls = []
    stub = make_stub([tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])], calls)
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    assert len(calls) == 1  # exact match -> no corrective retry


def test_row_guard_mismatch_nudges_with_confirmed_rows():
    calls = []
    stub = make_stub(
        [tool_reply(), tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    assert len(calls) == 2
    nudge = calls[1]["messages"][-1]
    assert nudge["role"] == "user"
    assert "2 baris" in nudge["content"]
    assert "Testing sistem" in nudge["content"]  # the nudge carries the actual rows


def test_row_guard_still_mismatched_refuses():
    calls = []
    stub = make_stub([tool_reply(), tool_reply()], calls)
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["function_name"] == ""
    assert env["arguments"] == ""
    assert "1 panggilan vs 2 baris" in env["reply"]
    assert "Tidak ada data yang dikirim" in env["reply"]
    assert len(calls) == 2
    assert env["history"][-1] == {"role": "assistant", "content": env["reply"]}


def test_row_guard_extra_call_refuses():
    calls = []
    three = tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS, SAMPLE_ARGUMENTS])
    stub = make_stub([three, three], calls)
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "error"
    assert "3 panggilan vs 2 baris" in env["reply"]
    assert len(calls) == 2


def test_row_guard_field_drift_recovers_after_nudge():
    # Two rows, right count, but row 2's jam_mulai drifted from 16:30 to
    # 16:00. Format-valid, so only equality against the confirmed summary
    # can catch it.
    calls = []
    stub = make_stub(
        [
            tool_reply_multi([SAMPLE_ARGUMENTS, DRIFTED_ROW2_ARGUMENTS]),
            tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS]),
        ],
        calls,
    )
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    rows = json.loads(env["arguments"])
    assert len(rows) == 2
    assert rows[1]["jam_mulai"] == "16:30"
    assert len(calls) == 2


def test_row_guard_fr05_shrink_recovered():
    # FR-05 retry clears its errors but drops a row; the row guard must
    # still recover the confirmed batch.
    calls = []
    stub = make_stub(
        [
            tool_reply_multi([SAMPLE_ARGUMENTS, INVALID_ARGUMENTS]),  # FR-05 retry
            tool_reply(),                                             # shrinks to 1
            tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS]),     # nudge recovers
        ],
        calls,
    )
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    assert len(calls) == 3
```

Note: `TWO_ROW_SUMMARY` is written so `parse_summary` reproduces `SAMPLE_ARGUMENTS` and `ROW2_ARGUMENTS` exactly — the "matching" tests depend on that.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_agent.py -k "row_guard or confirmed_rows" -v`
Expected: 6 FAILED, 1 PASSED — `ImportError: cannot import name '_confirmed_rows'` for the unit test, `assert env["type"] == "error"` (got `"function_call"` with a wrong/partial batch) for the guard tests; `test_row_guard_matching_rows_pass_without_nudge` already passes on today's code (it is the regression guard proving a correct 2-call reply needs no nudge).

- [ ] **Step 3: Write the helpers**

Add the import at the top of `src/alokasi_agent/agent.py` (next to the other `alokasi_agent` imports, lines 9-12):

```python
from alokasi_agent.eval import parse_summary
```

Insert after `_employee_problem` (after `src/alokasi_agent/agent.py:102`), before `def run(`:

```python
def _confirmed_rows(history: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """Structured rows from the pending confirmation summary, or [].

    The last assistant turn is the summary the user is confirming; eval's
    parse_summary turns its 'a | b | c | d | e' lines back into row dicts.
    [] means "nothing to compare against" (no summary, or one that will not
    parse), which turns the row guard off and keeps the old behaviour.
    """
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            return parse_summary(turn.get("content"))
    return []


def _same_rows(calls: list[dict[str, Any]], confirmed: list[dict[str, str]]) -> bool:
    """True when the model's calls are exactly the confirmed rows (any order)."""

    def canonical(rows):
        return sorted(
            json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows
        )

    emitted = [json.loads(tc["function"].get("arguments", "")) for tc in calls]
    return canonical(emitted) == canonical(confirmed)
```

Safe to call only when FR-05 validation already passed (every call's `arguments` parses) — that is true wherever the guard runs (see Step 4).

- [ ] **Step 4: Replace the decision chain head**

In `run()`, replace this block (currently `agent.py:157-172`):

```python
    if any(errors_by_id.values()):
        # Still malformed after the retry: refuse instead of sending a partial call.
        errors = [
            error for tc in calls for error in errors_by_id.get(tc.get("id", ""), [])
        ]
        reason = "Data tidak valid setelah dicoba ulang: " + "; ".join(errors)
        envelope = {
            "success": False,
            "type": "error",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": reason,
        }
        history_content: str = reason
    elif calls and (employee_question := _employee_problem(calls, employees)):
```

with:

```python
    confirmed = _confirmed_rows(prior)
    refuse_reason = ""
    if any(errors_by_id.values()):
        # Still malformed after the retry: refuse instead of sending a partial call.
        errors = [
            error for tc in calls for error in errors_by_id.get(tc.get("id", ""), [])
        ]
        refuse_reason = "Data tidak valid setelah dicoba ulang: " + "; ".join(errors)
    elif calls and confirmed and not _same_rows(calls, confirmed):
        # FR-08 row guard: the summary above IS what the user confirmed, so
        # the calls must match it exactly — count and every field. Nudge once
        # with the confirmed rows; if they still differ, refuse rather than
        # write rows the user never saw.
        messages = messages + [
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
            },
            *[
                {"role": "tool", "tool_call_id": tc.get("id", ""), "content": "OK"}
                for tc in message.get("tool_calls") or []
            ],
            {
                "role": "user",
                "content": (
                    f"Konfirmasi tadi menampilkan {len(confirmed)} baris dengan "
                    f"isi berikut:\n"
                    f"{json.dumps(confirmed, ensure_ascii=False)}\n"
                    f"Tapi kamu mengirim {len(calls)} panggilan atau nilainya "
                    f"berbeda. Kirim ulang tepat {len(confirmed)} panggilan "
                    "create_alokasi, satu per baris, persis seperti di atas."
                ),
            },
        ]
        response = complete(messages, tools=tools)
        message = response["choices"][0]["message"]
        calls = _alokasi_calls(message)
        errors_by_id = _validate_calls(calls)
        # Short-circuit: with any error present the calls do not all parse,
        # so _same_rows must not run.
        if any(errors_by_id.values()) or not _same_rows(calls, confirmed):
            refuse_reason = (
                f"Isi alokasi tidak sesuai konfirmasi ({len(calls)} panggilan vs "
                f"{len(confirmed)} baris, atau nilainya berbeda). "
                "Tidak ada data yang dikirim."
            )

    if refuse_reason:
        envelope = {
            "success": False,
            "type": "error",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": refuse_reason,
        }
        history_content = refuse_reason
    elif calls and (employee_question := _employee_problem(calls, employees)):
```

Everything after that `elif` (employee/project checks, `elif calls:` → `function_call`, `else` → `text`, `new_history`, `envelope["history"]`) stays unchanged. The guard sits *after* the existing FR-05 retry block (`agent.py:138-155`), reuses its message shape, and re-validates — so an FR-05 shrink lands in the same guard. `confirmed == []` (no summary, unparseable summary, empty history) means the guard is off and behaviour is exactly as before.

- [ ] **Step 5: Run the new tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_agent.py -k "row_guard or confirmed_rows" -v`
Expected: 7 passed.

- [ ] **Step 6: Run the whole suite for regressions**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: 130 passed (123 + 7). In particular `test_multi_row_invalid_twice_returns_error_envelope` must still see its `"Data tidak valid setelah dicoba ulang"` prefix, and every existing multi-row test (history empty → `confirmed == []` → guard off) must be untouched.

---

### Task 2: `main.py` per-row POST isolation + error history fallback

**Files:**
- Modify: `main.py:153-198` (init vars, `fallback_history`) and `main.py:230-257` (POST loop), `main.py:267-280` (except block)
- Test: create `tests/test_main_chat.py`

**Interfaces:**
- Consumes: `run()` envelope (Task 1 unchanged shape); Flask app in `main.py`.
- Produces: `/chat` response — `hasil_ci3` is an array of per-row results where a failed row is `{"success": False, "message": "Baris N gagal dikirim ke ERP"}`; the `error` envelope's `history` is the updated history from `run()` when it got that far, else the input history.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main_chat.py`:

```python
"""The /chat write path: one POST per row, and history survives ERP errors."""
import json
import sys
import types

import pytest
import requests
from flask import Blueprint

# main.py imports server-only blueprints from /var/www/html/...; give them
# stubs so `import main` works on a dev machine.
if "modules.proyek" not in sys.modules:
    _modules_pkg = types.ModuleType("modules")
    _proyek_mod = types.ModuleType("modules.proyek")
    _proyek_mod.proyek_bp = Blueprint("proyek", __name__)
    _proyek_mod.controller = types.SimpleNamespace()
    _karyawan_mod = types.ModuleType("modules.karyawan")
    _karyawan_mod.karyawan_bp = Blueprint("karyawan", __name__)
    _routes_mod = types.ModuleType("modules.karyawan.routes")
    _routes_mod.controller = types.SimpleNamespace()
    _karyawan_mod.routes = _routes_mod
    sys.modules.update({
        "modules": _modules_pkg,
        "modules.proyek": _proyek_mod,
        "modules.karyawan": _karyawan_mod,
        "modules.karyawan.routes": _routes_mod,
    })

import main  # noqa: E402

ROW1 = {"nama_karyawan": "Imam Ihsani", "nama_proyek": "OPRS Divisi WIN 2026"}
ROW2 = {"nama_karyawan": "Budi Santoso", "nama_proyek": "OPRS Divisi WIN 2026"}
TWO_ROW_ARGUMENTS = json.dumps([ROW1, ROW2])
OK_RESPONSE = types.SimpleNamespace(status_code=200, json=lambda: {"success": True})


def envelope_with(arguments, history=None):
    """A run() stub whose envelope carries `arguments` and `history`."""
    def fake_run(*args, **kwargs):
        envelope = {
            "success": True,
            "type": "function_call",
            "function_name": "create_alokasi",
            "arguments": arguments,
            "reply": None,
            "history": history or [],
        }
        return envelope, envelope["history"]
    return fake_run


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "get_projects", lambda: [])
    monkeypatch.setattr(main, "get_employees", lambda: [])
    monkeypatch.setattr(main, "get_erp_token", lambda: "token-test")
    monkeypatch.setattr(
        main.requests, "get",
        lambda *args, **kwargs: types.SimpleNamespace(status_code=200, text="ok"),
    )
    main.app.config["TESTING"] = True
    with main.app.test_client() as test_client:
        yield test_client


def test_second_row_failure_still_reports_first_row(client, monkeypatch):
    monkeypatch.setattr(main, "run", envelope_with(TWO_ROW_ARGUMENTS))
    replies = [OK_RESPONSE, requests.exceptions.ConnectionError("erp down")]

    def fake_post(*args, **kwargs):
        item = replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(main.requests, "post", fake_post)
    data = client.post("/chat", json={"message": "ya"}).get_json()
    assert data["success"] is True
    assert data["type"] == "function_call"
    assert len(data["hasil_ci3"]) == 2
    assert data["hasil_ci3"][0] == {"success": True}
    assert data["hasil_ci3"][1]["success"] is False
    assert "Baris 2" in data["hasil_ci3"][1]["message"]


def test_single_row_keeps_object_hasil_ci3(client, monkeypatch):
    monkeypatch.setattr(main, "run", envelope_with(json.dumps(ROW1)))
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: OK_RESPONSE)
    data = client.post("/chat", json={"message": "ya"}).get_json()
    assert data["type"] == "function_call"
    assert isinstance(data["hasil_ci3"], dict)
    assert data["hasil_ci3"]["success"] is True


def test_erp_error_returns_the_updated_history(client, monkeypatch):
    history = [
        {"role": "user", "content": "ya"},
        {"role": "assistant", "content": ""},
    ]
    monkeypatch.setattr(main, "run", envelope_with(TWO_ROW_ARGUMENTS, history=history))

    def raise_get(*args, **kwargs):
        raise RuntimeError("validate down")

    monkeypatch.setattr(main.requests, "get", raise_get)
    sent = [{"role": "user", "content": "old history"}]
    data = client.post("/chat", json={"message": "ya", "history": sent}).get_json()
    assert data["type"] == "error"
    assert data["history"] == history
```

- [ ] **Step 2: Run the tests to verify the failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main_chat.py -v`
Expected: `test_second_row_failure_still_reports_first_row` FAILS (today the raised POST falls into the outer `except`, returning `success: False` + generic reply), `test_erp_error_returns_the_updated_history` FAILS (today it echoes the *input* history), `test_single_row_keeps_object_hasil_ci3` PASSES (regression guard for the existing single-row shape).

- [ ] **Step 3: Init state before the `try` and track the updated history**

In `main.py`, replace the start of `chat()`:

```python
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(silent=True) or {}
```

with:

```python
@app.route("/chat", methods=["POST"])
def chat():
    user_message = ""
    user_id = None
    # Kalau terjadi error setelah run(), frontend tetap menerima history
    # yang sudah diperbarui — kalau tidak, giliran konfirmasi hilang.
    fallback_history = []
    try:
        data = request.get_json(silent=True) or {}
```

Then, in the body of `chat()`, replace:

```python
        envelope, _history = run(
            user_message,
            user_name=data.get("user_name") or "",
            employees=employees,
            projects=projects,
            history=data.get("history") or [],
            user_id=user_id,
        )
        body = dict(envelope)
```

with:

```python
        fallback_history = data.get("history") or []
        envelope, _history = run(
            user_message,
            user_name=data.get("user_name") or "",
            employees=employees,
            projects=projects,
            history=data.get("history") or [],
            user_id=user_id,
        )
        body = dict(envelope)
        fallback_history = body.get("history") or fallback_history
```

And in the `except` block, replace `"history": data.get("history") or []` with `"history": fallback_history`.

- [ ] **Step 4: Isolate each row's POST**

In `main.py`, replace the loop (currently lines 230-252):

```python
            #++VVVVVV Kirim data ke API ERP CI3
            # One POST per row.
            results = []
            for row in rows:
                response_ci3 = requests.post(
                    "https://appweb.mitrasinergi.co.id/msa/apiv1/aialokasiharian/createAlokasi",
                    json=row,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )

                #++VVVVVV DEBUG RESPONSE
                print("CI3 HTTP STATUS:", response_ci3.status_code)
                print("CI3 RESPONSE:", response_ci3.text)
                #//++VVVVVV

                #++VVVVVV Ambil response dari API ERP CI3
                hasil_ci3 = response_ci3.json()
                results.append(hasil_ci3)
                #//++VVVVVV
```

with:

```python
            #++VVVVVV Kirim data ke API ERP CI3
            # One POST per row. A failed row becomes its own result so the
            # rows already written stay visible instead of vanishing behind
            # a generic error.
            results = []
            for index, row in enumerate(rows, start=1):
                try:
                    response_ci3 = requests.post(
                        "https://appweb.mitrasinergi.co.id/msa/apiv1/aialokasiharian/createAlokasi",
                        json=row,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json"
                        },
                        timeout=30
                    )

                    #++VVVVVV DEBUG RESPONSE
                    print("CI3 HTTP STATUS:", response_ci3.status_code)
                    print("CI3 RESPONSE:", response_ci3.text)
                    #//++VVVVVV

                    hasil_ci3 = response_ci3.json()
                except Exception as error:
                    print(f"CI3 row {index} error:", repr(error))
                    hasil_ci3 = {
                        "success": False,
                        "message": f"Baris {index} gagal dikirim ke ERP",
                    }
                results.append(hasil_ci3)
```

The lines after the loop (`body["hasil_ci3"] = results[0] if single_row else results`, `return jsonify(body)`) stay unchanged.

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_main_chat.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: 133 passed (130 + 3).

---

### Task 3: Document the behaviour (FRD + integration guide)

**Files:**
- Modify: `PRD_FRD_create_alokasi_agent.md` (FR-08, after the Decision line ~231)
- Modify: `docs/integration-guide.md` (multi-row bullet ~194-198; troubleshooting table ~581)

**Interfaces:**
- Consumes: the code shipped in Tasks 1-2.
- Produces: nothing executable — docs only.

- [ ] **Step 1: FRD addendum**

Insert directly after the FR-08 `> **Decision (2026-10-01): parallel calls per row.** ...` line:

```markdown
> **Addendum (2026-10-14): insert must equal the confirmed summary.** `run()` parses the last assistant confirmation back into rows (`_confirmed_rows` → `parse_summary` in `src/alokasi_agent/agent.py`) and requires the confirm turn's `create_alokasi` calls to match those rows exactly — count and every field, order-insensitive. A mismatch gets one corrective retry carrying the confirmed rows as JSON; if it still differs, `run()` refuses with an error envelope and nothing is written (this also catches the FR-05 retry silently dropping a row). Pinned by the `test_row_guard_*` tests in `tests/test_agent.py`. `main.py` isolates each ERP POST: a failed row returns as its own `{"success": false, ...}` entry inside `hasil_ci3` (the other rows stay as the ERP returned them), and an ERP error returns the updated `history`.
```

- [ ] **Step 2: Integration guide — multi-row bullet**

Extend the **Multi-row** bullet (ends with `(PRD FR-08.)`) with one sentence:

```markdown
  If one row's POST fails, that entry of `hasil_ci3` is
  `{"success": false, "message": "Baris N gagal dikirim ke ERP"}` while the
  other entries stay as the ERP returned them — render each row's own result.
```

- [ ] **Step 3: Integration guide — troubleshooting row**

Add one row to the Troubleshooting table, after `| You expected a write but none happened | ...`:

```markdown
| Confirmation lists 2 rows but only 1 (or 3, or altered values) gets written | The confirm turn's rows no longer match the confirmed summary. Since 2026-10-14 the agent nudges once with the exact confirmed rows and then refuses with an error — nothing partial is written. If you see a partial write, the server is running old code: deploy the current `main.py` + `src/` and confirm the server copy matches this repo (`main.py:14` loads the server's own `.env`). |
```

---

### Task 4: Verification

**Files:** none changed.

- [ ] **Step 1: Full unit suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: 133 passed, 0 failed.

- [ ] **Step 2: Live single-row smoke (needs `OPENAI_API_KEY`)**

Run: `.venv\Scripts\python.exe scripts\smoke_agent.py`
Expected: exit 0 — confirms the guard did not break the normal one-row confirm flow against the real model.

- [ ] **Step 3: Live multi-allocation eval (needs `OPENAI_API_KEY`)**

Run: `.venv\Scripts\python.exe scripts\run_eval.py --category multi_allocation`
Expected: same or better than the last run's 6/6 rows (this rewrites `eval/results.json`; a drop means the guard misfired on a real summary and `parse_summary` vs the model's calls needs a look — check the refusal `reply` text the eval reports).

- [ ] **Step 4: Deployment check (manual, on the server)**

The repo cannot see the deployed code. Confirm with the user that the server's `main.py` and `src/` match this working copy (same git commit), since the reported "confirmed 2, inserted 1" can also be a stale deploy missing the FR-08 array loop entirely. Then reproduce the original failing input through the real frontend once — expected: both confirmed rows appear in `hasil_ci3`, or an Indonesian refusal with **no** rows written.

---

## Residual risks (accepted, not in scope)

- **Turn-1 under-extraction** ("only one line shown in the first confirmation") cannot be guarded server-side: on the extraction turn there is no reference to compare against — the model may show fewer rows than the message contained. Prompt rule ("several separate tasks → separate records") plus the eval's 6/6 turn-1 rate are the current mitigation.
- **Unparseable summary → guard off.** `parse_summary` returns `[]` if any summary-shaped line is malformed; the guard then behaves exactly as today's code (documented in `_confirmed_rows`'s docstring).
- **Frontend history threading** is outside this repo; if the caller drops `history`, there is no confirmed summary and the guard is off (documented in the integration guide troubleshooting table).
- `_alokasi_calls` still silently ignores a call to any other function name (`agent.py:15-26`) — only `create_alokasi` is ever offered, and the row guard now catches the resulting mismatch anyway.
