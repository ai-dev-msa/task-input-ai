# find_employee / find_project Lookup Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the full employee/project lists from the system prompt and resolve names through `find_employee` / `find_project` tool calls that code (difflib) answers, injecting only the matched canonical name back to the LLM.

**Architecture:** The caller still sends `employees`/`projects` to `run()` (no DB lookups, PRD §6). The prompt loses its list slots; the model must resolve names via two new lookup tools. A bounded round-loop in `run()` dispatches tool calls: `find_*` gets a difflib match result, `create_alokasi` with an unresolved name gets a redirect tool-error back to `find_*` (fail-closed, max 2 redirects), then validation/guard/accept as today.

**Tech Stack:** Python 3 (stdlib `difflib`, no new dependencies), pytest, OpenAI chat-completions tools. Spec: `docs/superpowers/specs/2026-10-16-find-tool-lookup-design.md`.

## Global Constraints

- **Do not commit anything (AGENTS.md).** No task contains a git-commit step; the user commits when they choose.
- **Test command:** `.venv\Scripts\python.exe -m pytest --ignore=tests\test_main_chat.py` — `test_main_chat.py` has a pre-existing collection error (server-only `modules.*` imports) that is out of scope. The suite baseline before this plan: 6 pre-existing `test_prompt.py` failures (from the user's uncommitted prompt rewrite), 133 passed. Those 6 are fixed by Task 3.
- **`src/alokasi_agent/prompt.py` has an uncommitted user rewrite in the working tree.** Edit on top of it; never restore the committed version.
- **The full endpoint list must NEVER be injected into the system prompt** (hard requirement, pinned by tests).
- Plain functions, no classes, no new dependencies, beginner-readable code (AGENTS.md).
- Tool-result and redirect strings are pinned by tests — use them byte-for-byte.
- `build_system_prompt(now, user_name)` is the new signature (lists removed); all call sites must be updated in Task 3.

---

### Task 1: `find_employee` / `find_project` tool contracts

**Files:**
- Modify: `src/alokasi_agent/schema.py` (append after `CREATE_ALOKASI_TOOL`, before `_is_real_date`)
- Test: `tests/test_schema.py` (append)

**Interfaces:**
- Consumes: nothing (schema is dependency-free).
- Produces: module-level dicts `FIND_EMPLOYEE_TOOL` and `FIND_PROJECT_TOOL` with keys `name`, `description`, `input_schema` (provider-neutral, same shape as `CREATE_ALOKASI_TOOL`). Task 4 imports them from `alokasi_agent.schema`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_schema.py`:

```python
from alokasi_agent.schema import FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL


def test_find_tools_share_one_shape():
    for tool, name, title in (
        (FIND_EMPLOYEE_TOOL, "find_employee", "FindEmployeeArgs"),
        (FIND_PROJECT_TOOL, "find_project", "FindProjectArgs"),
    ):
        assert tool["name"] == name
        assert tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert schema["title"] == title
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["name"]
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["name"]["minLength"] == 1


def test_find_tools_names_do_not_collide_with_create():
    assert FIND_EMPLOYEE_TOOL["name"] != CREATE_ALOKASI_TOOL["name"]
    assert FIND_PROJECT_TOOL["name"] != CREATE_ALOKASI_TOOL["name"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\test_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'FIND_EMPLOYEE_TOOL'`

- [ ] **Step 3: Implement the tool contracts**

Append to `src/alokasi_agent/schema.py`, immediately after the `CREATE_ALOKASI_TOOL` dict:

```python
FIND_EMPLOYEE_DESCRIPTION = (
    "Cocokkan nama dengan daftar karyawan. Panggil untuk setiap nama_karyawan "
    "dan setiap anggota tim_pekerjaan sebelum create_alokasi; gunakan ejaan "
    "yang dikembalikan alat ini."
)

FIND_EMPLOYEE_TOOL = {
    "name": "find_employee",
    "description": FIND_EMPLOYEE_DESCRIPTION,
    "input_schema": {
        "additionalProperties": False,
        "properties": {
            "name": {
                "description": "Nama karyawan sesuai tulisan user, contoh: Imam Ihsani",
                "minLength": 1,
                "title": "Name",
                "type": "string",
            },
        },
        "required": ["name"],
        "title": "FindEmployeeArgs",
        "type": "object",
    },
}

FIND_PROJECT_TOOL = {
    "name": "find_project",
    "description": (
        "Cocokkan nama dengan daftar proyek. Panggil untuk setiap nama_proyek "
        "sebelum create_alokasi; gunakan ejaan yang dikembalikan alat ini."
    ),
    "input_schema": {
        "additionalProperties": False,
        "properties": {
            "name": {
                "description": "Nama proyek sesuai tulisan user, contoh: OPRS Divisi WIN 2026",
                "minLength": 1,
                "title": "Name",
                "type": "string",
            },
        },
        "required": ["name"],
        "title": "FindProjectArgs",
        "type": "object",
    },
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\test_schema.py -q`
Expected: PASS (existing schema tests + 2 new)

---

### Task 2: `to_openai_tools` accepts multiple tools

**Files:**
- Modify: `src/alokasi_agent/llm.py:50-60`
- Test: `tests/test_llm.py` (append)

**Interfaces:**
- Consumes: `FIND_EMPLOYEE_TOOL`, `FIND_PROJECT_TOOL` from Task 1 (test only).
- Produces: `to_openai_tools(*tools) -> list[dict]` — variadic; single-argument calls (existing code/tests) keep working unchanged. Task 4 calls it with three tools.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm.py`:

```python
from alokasi_agent.schema import FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL


def test_to_openai_tools_accepts_multiple_tools():
    tools = to_openai_tools(CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL)
    assert [t["function"]["name"] for t in tools] == [
        "create_alokasi",
        "find_employee",
        "find_project",
    ]
    assert all(t["type"] == "function" for t in tools)
    assert tools[1]["function"]["parameters"] == FIND_EMPLOYEE_TOOL["input_schema"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests\test_llm.py::test_to_openai_tools_accepts_multiple_tools -q`
Expected: FAIL — `TypeError` (positional argument 2)

- [ ] **Step 3: Implement variadic `to_openai_tools`**

Replace `src/alokasi_agent/llm.py:50-60` with:

```python
def to_openai_tools(*tools: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\test_llm.py -q`
Expected: PASS (all existing + new)

---

### Task 3: Remove the lists from the prompt (and fix every call site)

**Files:**
- Modify: `src/alokasi_agent/prompt.py` (template + `build_system_prompt` + one comment)
- Modify: `src/alokasi_agent/agent.py:231-233` (call-site only — no loop changes yet)
- Modify: `scripts/smoke_llm.py:55,60` and its schema import
- Test: rewrite `tests/test_prompt.py` (whole file given below)
- Test: `tests/test_agent.py:229-236` (one test rewritten)

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_system_prompt(now: datetime, user_name: str) -> str`. Task 4 relies on this signature. Prompt text now contains `find_employee`/`find_project` rules and no list slots.

- [ ] **Step 1: Rewrite `tests/test_prompt.py`**

Replace the whole file with:

```python
import inspect
from datetime import datetime, timedelta, timezone

from alokasi_agent.prompt import PROMPT_TEMPLATE, build_system_prompt

USER = "Andi Wijaya"


def build(now: datetime) -> str:
    return build_system_prompt(now, USER)


def test_no_leftover_placeholders():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "{{" not in out
    assert "}}" not in out


def test_pinned_wib_format():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Rabu, 30 September 2026, 14:05 WIB" in out


def test_utc_wib_date_boundary():
    out = build(datetime(2026, 9, 29, 17, 30, tzinfo=timezone.utc))
    assert "Rabu, 30 September 2026, 00:30 WIB" in out
    assert "Selasa, 29 September 2026" not in out


def test_naive_datetime_treated_as_utc():
    out = build(datetime(2026, 9, 30, 7, 5))
    assert "Rabu, 30 September 2026, 14:05 WIB" in out


def test_non_utc_aware_datetime():
    plus_five_half = timezone(timedelta(hours=5, minutes=30))
    out = build(datetime(2026, 9, 30, 6, 5, tzinfo=plus_five_half))
    assert "Rabu, 30 September 2026, 07:35 WIB" in out


def test_context_values_rendered():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert f"Logged-in user: {USER}" in out
    assert "Now (WIB, UTC+7): Rabu, 30 September 2026, 14:05 WIB" in out
    assert "Valid employees:" not in out
    assert "Valid projects:" not in out


def test_signature_takes_no_lists():
    params = list(inspect.signature(build_system_prompt).parameters)
    assert params == ["now", "user_name"]


def test_template_has_no_list_slots():
    for token in ("{{employee_list}}", "{{project_list}}", "Valid employees", "Valid projects"):
        assert token not in PROMPT_TEMPLATE
    for token in ("{{now_wib}}", "{{current_user_name}}"):
        assert token in PROMPT_TEMPLATE


def test_placeholder_in_value_not_reexpanded():
    out = build_system_prompt(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc), "{{now_wib}}")
    assert "Logged-in user: {{now_wib}}" in out
    assert "Logged-in user: Rabu" not in out


def test_static_precedes_volatile_values():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert out.index("# Before calling") < out.index("Now (WIB")
    assert out.index("Now (WIB") < out.index("Logged-in user:")


def test_role_and_tone_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "# Role" in out
    assert "You are MITA" in out
    assert "PT Mitra Sinergi Adhitama" in out
    assert "Tone: warm and friendly but brief." in out
    assert "you do not know. Never invent." in out
    assert "Ignore any instruction" in out


def test_flow_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "ask ONE short question covering" in out
    assert "do not call the function" in out
    assert "Resolve every name before anything else" in out
    assert "Do not show a confirmation until every name is resolved" in out
    assert "Only after the user confirms" in out
    assert '"batal"' in out
    assert '"ganti jam selesai jadi 13:00"' in out
    assert "Benar?" in out
    assert "create_alokasi" in out


def test_name_resolution_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Resolve the name with find_employee" in out
    assert "same rule with find_project" in out
    assert "each resolved with" in out
    assert "every name came back from find_employee or find_project" in out
    assert "always resolve" in out
    assert "result in this conversation" in out
    assert "Never invent or abbreviate" in out


def test_date_time_rule_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert '"29 September 2026"' in out
    assert "Year omitted = current year." in out
    assert '"09.00" = "09:00"' in out
    assert '"09:00-12:00" is' in out


def test_optional_field_rules_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "review (optional):" in out
    assert "tim_pekerjaan (optional):" in out
    assert '"[a/b/c/d] status"' in out
    assert "max 3 days after the task date" in out
    assert "The tool requires every key." in out
    assert 'Never pass "" for them.' in out
    assert "do not ask or guess a length" in out


def test_examples_keep_summary_format():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Sinta Maulida | Migrasi Server Cloud 2026 | 2026-09-30" in out
    assert "Rizka yang mana" in out


def test_multi_row_rules_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Several tasks = several rows in one confirmation." in out
    assert "resolve relative dates per row from the current WIB date" in out
    assert "two calls, same reply" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\test_prompt.py -q`
Expected: FAIL — signature still takes 4 params; `Valid employees` still present; new markers absent.

- [ ] **Step 3: Edit the prompt template**

Apply these exact edits to `src/alokasi_agent/prompt.py` `PROMPT_TEMPLATE` (working-tree version):

**Edit A — insert resolve step and renumber.** Replace:

```
3. If everything is resolved, show one line per row and ask to confirm:
```

with:

```
3. Resolve every name before anything else: call find_employee for the assignee
   and each tim_pekerjaan member, and find_project for the project, and use only
   the spelling the tool returned. When it returns candidates, ask the user which
   one it is; when it finds nothing, ask the user to recheck. Do not show a
   confirmation until every name is resolved.
4. If everything is resolved, show one line per row and ask to confirm:
```

Then renumber the following steps (each is a single occurrence; the text before `:` stays identical):

- `4. Edit instead of confirmation ("ganti jam selesai jadi 13:00"): update that` → `5. Edit instead of confirmation ("ganti jam selesai jadi 13:00"): update that`
- `5. Cancel ("batal", "gak jadi"): one short line, no call.` → `6. Cancel ("batal", "gak jadi"): one short line, no call.`
- `6. Only after the user confirms: call` → `7. Only after the user confirms: call`

**Edit B — scope line.** Replace:

```
- Questions answerable from the data in this prompt (employees, projects,
  logged-in user, date/time): answer in one line.
```

with:

```
- Questions answerable from this prompt or from a find_employee/find_project
  result in this conversation (logged-in user, date/time): answer in one line.
```

**Edit C — nama_karyawan / nama_proyek rules.** Replace:

```
nama_karyawan: the assignee, not the sender. "saya/aku/gue" or nobody named =
  logged-in user. Must match the employee list exactly; copy the full name as
  listed. Fix casing/typos or accept a first name only when exactly one
  employee fits; if 2+ or none fit, ask.
nama_proyek: same matching rule against the project list. Never invent or
  abbreviate.
```

with:

```
nama_karyawan: the assignee, not the sender. "saya/aku/gue" or nobody named =
  logged-in user. Resolve the name with find_employee and copy the spelling it
  returns; when it gives candidates, ask which one; when it finds nothing, ask
  the user to recheck. Never invent a name.
nama_proyek: same rule with find_project. Never invent or abbreviate.
```

**Edit D — tim_pekerjaan rule.** Replace:

```
tim_pekerjaan (optional): comma-separated team members, each matching the
  employee list exactly (same rule as nama_karyawan).
```

with:

```
tim_pekerjaan (optional): comma-separated team members, each resolved with
  find_employee (same rule as nama_karyawan); when one cannot be resolved, ask
  the user to fix the name or drop it from the team.
```

**Edit E — Before calling.** Replace:

```
Call only if: names match the lists character for character; tanggal is a real
date; jam_selesai (if not null) is after jam_mulai; jenis_pekerjaan is only what
```

with:

```
Call only if: every name came back from find_employee or find_project; tanggal
is a real date; jam_selesai (if not null) is after jam_mulai; jenis_pekerjaan is only what
```

**Edit F — examples intro.** Replace:

```
2026-09-30. Names and projects in examples are illustrative: always use the
lists below.
```

with:

```
2026-09-30. Names and projects in examples are illustrative: always resolve
real names through find_employee/find_project first.
```

**Edit G — context slots (the hard requirement).** Replace:

```
# Context for this request
Valid employees: {{employee_list}}
Valid projects: {{project_list}}
Now (WIB, UTC+7): {{now_wib}}
```

with:

```
# Context for this request
Now (WIB, UTC+7): {{now_wib}}
```

**Edit H — signature and values.** In `prompt.py`:

1. Remove the now-unused import: delete `from collections.abc import Sequence`.
2. Change the def line to:

```python
def build_system_prompt(now: datetime, user_name: str) -> str:
```

3. In the `values` dict, delete these two lines:

```python
        "employee_list": ", ".join(employees),
        "project_list": ", ".join(projects),
```

**Edit I — comment accuracy.** Line 10 comment `# Summary-line shapes for parse_summary (rule 3 in the template below).` → `# Summary-line shapes for parse_summary (rule 4 in the template below).`

- [ ] **Step 4: Fix the `agent.py` call site (signature only)**

Replace `src/alokasi_agent/agent.py:231-233`:

```python
    system = build_system_prompt(
        now or datetime.now(timezone.utc), user_name, employees, projects
    )
```

with:

```python
    system = build_system_prompt(now or datetime.now(timezone.utc), user_name)
```

- [ ] **Step 5: Fix `scripts/smoke_llm.py`**

1. Change the schema import to: `from alokasi_agent.schema import CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL`
2. In `build_request`, replace:

```python
    system = build_system_prompt(datetime.now(timezone.utc), user, employees, projects)
```

with:

```python
    system = build_system_prompt(datetime.now(timezone.utc), user)
```

3. Replace `return messages, to_openai_tools(CREATE_ALOKASI_TOOL)` with:

```python
    return messages, to_openai_tools(CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL)
```

(The `employees`/`projects` parameters of `build_request` become unused by it — leave the signature alone; `main()` still passes them and other code paths may grow.)

- [ ] **Step 6: Run the prompt tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\test_prompt.py -q`
Expected: PASS (all).

- [ ] **Step 7: Update the injected-context test in `test_agent.py`**

Replace `tests/test_agent.py:229-236` (`test_system_prompt_carries_injected_context`) with:

```python
def test_system_prompt_never_carries_the_lists():
    calls = []
    call_run(make_stub([text_reply("ok")], calls))
    system = calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "Rabu, 30 September 2026, 14:05 WIB" in system["content"]
    assert f"Logged-in user: {USER}" in system["content"]
    assert "Valid employees" not in system["content"]
    assert "Valid projects" not in system["content"]
```

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest --ignore=tests\test_main_chat.py -q`
Expected: PASS (0 failed). Membership/loop behavior is unchanged at this point — only the prompt and signatures moved.

---

### Task 4: Lookup dispatch + redirect loop in `agent.py`

**Files:**
- Modify: `src/alokasi_agent/agent.py` (helpers + `run()` loop)
- Test: `tests/test_agent.py` (new tests + rewrites listed below)

**Interfaces:**
- Consumes: `FIND_EMPLOYEE_TOOL`, `FIND_PROJECT_TOOL` (Task 1), variadic `to_openai_tools` (Task 2), `build_system_prompt(now, user_name)` (Task 3).
- Produces: module-level `MAX_ROUNDS = 6`; functions `_find_calls(message) -> list[tuple[str, str, str]]` (id, tool name, name), `_resolve_name(value, tool_name, valid) -> str`, `_missing_names(values, valid) -> list[str]`, `_redirect_problems(calls, employees, projects) -> dict[str, str]` (call id → Indonesian redirect sentence, `""` for clean calls). `_list_problem`, `_employee_problem`, `_project_problem`, `_tim_problem` are **deleted** (grep to confirm no other users).

- [ ] **Step 1: Write the failing tests**

**1a. Add helpers** to `tests/test_agent.py` right after `tool_reply_multi`:

```python
def find_reply(tool_name, name, call_id="call_f1"):
    return {
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": json.dumps({"name": name})},
            }
        ],
    }
```

**1b. Update the tools-contract test** (`tests/test_agent.py:239-242`) to:

```python
def test_tools_attached_match_contract():
    calls = []
    call_run(make_stub([text_reply("ok")], calls))
    assert calls[0]["tools"] == to_openai_tools(
        CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL
    )
```

and add `FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL` to the existing `from alokasi_agent.schema import CREATE_ALOKASI_TOOL` line.

**1c. Add unit tests.** First extend the top-of-file imports in `tests/test_agent.py`: change `from alokasi_agent import run` to:

```python
from alokasi_agent import run
from alokasi_agent.agent import _find_calls, _resolve_name
```

Then append a new section:

```python
# --- find_* name resolution (difflib, no LLM) ---

def test_resolve_name_exact_match_returns_canonical_spelling():
    assert _resolve_name("imam ihsani", "find_employee", EMPLOYEES) == "Matched: Imam Ihsani"


def test_resolve_name_returns_candidates_for_near_match():
    result = _resolve_name("Imam", "find_employee", ["Imam Ihsani", "Imam Hidayat"])
    assert result.startswith('No exact match for "Imam". Closest: ')
    assert "Imam Ihsani" in result and "Imam Hidayat" in result
    assert result.endswith("Ask the user which one is meant.")


def test_resolve_name_not_found():
    assert _resolve_name("zzz qqq", "find_project", PROJECTS) == (
        '"zzz qqq" not found in the project list. Ask the user to check the spelling.'
    )


def test_resolve_name_empty_list_is_unavailable():
    assert _resolve_name("Anyone", "find_employee", []) == (
        "The employee list is unavailable, try again later."
    )


def test_resolve_name_unreadable_name_asks_to_retry():
    assert _resolve_name("", "find_employee", EMPLOYEES) == (
        'Could not read the name. Call again with {"name": "..."} as plain text.'
    )


def test_find_call_with_bad_json_reads_as_empty_name():
    message = {
        "tool_calls": [
            {
                "id": "call_x",
                "type": "function",
                "function": {"name": "find_employee", "arguments": "not json"},
            }
        ]
    }
    assert _find_calls(message) == [("call_x", "find_employee", "")]
```

**1d. Replace the membership "question" tests.** Delete/replace these existing tests with the versions below (keep every test not listed):

Delete:
- `test_unknown_project_becomes_question_not_call`
- `test_unknown_project_blocks_whole_batch`
- `test_no_close_candidate_still_asks`
- `test_multiple_candidates_offer_a_choice`
- `test_unknown_employee_becomes_question_not_call`
- `test_unknown_employee_blocks_whole_batch`
- `test_unknown_employee_no_close_candidate_still_asks`
- `test_unknown_employee_multiple_candidates_offer_a_choice`
- `test_unknown_tim_member_no_close_match_offers_delete`
- `test_unknown_tim_member_close_match_offers_delete`
- `test_unknown_tim_member_multiple_candidates_offer_choice`
- `test_unknown_tim_member_blocks_whole_batch`

Add in their place:

```python
# --- membership now redirects to find_* (fail closed) ---

def test_unknown_project_redirects_to_find_project():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "OPRS WIN")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_project", "OPRS WIN"),
         tool_reply()],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert env["arguments"] == SAMPLE_ARGUMENTS
    assert len(calls) == 3
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Proyek "OPRS WIN" belum dipastikan.' in round2_tools[0]["content"]
    assert "find_project" in round2_tools[0]["content"]
    round3_tools = [m for m in calls[2]["messages"] if m["role"] == "tool"]
    assert round3_tools[0]["content"] == "Matched: OPRS Divisi WIN 2026"


def test_unknown_project_blocks_whole_batch():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "Proyek Fiktif")
    calls = []
    stub = make_stub(
        [tool_reply_multi([SAMPLE_ARGUMENTS, bad]),
         find_reply("find_project", "Proyek Fiktif"),
         tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert round2_tools[0]["content"] == "OK"
    assert 'Proyek "Proyek Fiktif" belum dipastikan.' in round2_tools[1]["content"]


def test_no_close_candidate_ends_in_model_question():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "zzz qqq")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_project", "zzz qqq"),
         text_reply('Proyek "zzz qqq" nggak ada. Proyeknya yang mana?')],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "text"
    assert env["reply"] == 'Proyek "zzz qqq" nggak ada. Proyeknya yang mana?'
    round3_tools = [m for m in calls[2]["messages"] if m["role"] == "tool"]
    assert round3_tools[0]["content"] == (
        '"zzz qqq" not found in the project list. Ask the user to check the spelling.'
    )


def test_unknown_employee_redirects_to_find_employee():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "Imam")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_employee", "Imam"),
         tool_reply()],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert env["arguments"] == SAMPLE_ARGUMENTS
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Karyawan "Imam" belum dipastikan.' in round2_tools[0]["content"]
    assert "find_employee" in round2_tools[0]["content"]


def test_unknown_employee_blocks_whole_batch():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "Karyawan Fiktif")
    calls = []
    stub = make_stub(
        [tool_reply_multi([SAMPLE_ARGUMENTS, bad]),
         find_reply("find_employee", "Karyawan Fiktif"),
         tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Karyawan "Karyawan Fiktif" belum dipastikan.' in round2_tools[1]["content"]


def test_unknown_employee_no_close_candidate_ends_in_model_question():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "zzz qqq")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_employee", "zzz qqq"),
         text_reply('Karyawan "zzz qqq" nggak ada di daftar. Siapa namanya?')],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "text"
    assert env["reply"] == 'Karyawan "zzz qqq" nggak ada di daftar. Siapa namanya?'


def test_redirect_budget_exhaustion_refuses():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "Karyawan Fiktif")
    calls = []
    stub = make_stub([tool_reply(arguments=bad)] * 3, calls)
    env, _ = call_run(stub)
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["arguments"] == ""
    assert "Tidak ada data yang dikirim" in env["reply"]
    assert len(calls) == 3


def test_find_and_create_in_same_turn_replies_to_all():
    mixed = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_f1",
                "type": "function",
                "function": {
                    "name": "find_project",
                    "arguments": json.dumps({"name": "oprs divisi win 2026"}),
                },
            },
            {"id": "call_1", "type": "function",
             "function": {"name": "create_alokasi", "arguments": SAMPLE_ARGUMENTS}},
        ],
    }
    calls = []
    stub = make_stub([mixed, tool_reply()], calls)
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(calls) == 2
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in round2_tools] == ["call_f1", "call_1"]
    assert round2_tools[0]["content"] == "Matched: OPRS Divisi WIN 2026"
    assert round2_tools[1]["content"] == "OK"


def test_find_employee_with_empty_list_reports_unavailable():
    calls = []
    stub = make_stub(
        [find_reply("find_employee", "Anyone"), text_reply("Daftar belum siap, coba lagi.")],
        calls,
    )
    env, _ = call_run(stub, employees=[])
    assert env["type"] == "text"
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert round2_tools[0]["content"] == "The employee list is unavailable, try again later."
```

**1e. Replace the tim membership tests** (`test_unknown_tim_member_no_close_match_offers_delete`, `test_unknown_tim_member_close_match_offers_delete`, `test_unknown_tim_member_multiple_candidates_offer_choice`, `test_unknown_tim_member_blocks_whole_batch`) with:

```python
def test_unknown_tim_member_redirects_to_find_employee():
    calls = []
    stub = make_stub(
        [tool_reply(arguments=with_tim("Orang Asing")),
         find_reply("find_employee", "Orang Asing"),
         tool_reply(arguments=with_tim("Budi Santoso"))],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert json.loads(env["arguments"])["tim_pekerjaan"] == "Budi Santoso"
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Anggota tim "Orang Asing" belum dipastikan.' in round2_tools[0]["content"]
    assert "find_employee" in round2_tools[0]["content"]
    assert "minta user menghapusnya dari tim" in round2_tools[0]["content"]


def test_unknown_tim_member_blocks_whole_batch():
    good = SAMPLE_ARGUMENTS
    bad = with_tim("Orang Asing")
    calls = []
    stub = make_stub(
        [tool_reply_multi([good, bad]),
         find_reply("find_employee", "Orang Asing"),
         tool_reply_multi([good, with_tim("Budi Santoso")])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\test_agent.py -q`
Expected: FAIL — `ImportError: cannot import name '_resolve_name'` (and the replaced tests fail until the loop lands).

- [ ] **Step 3: Implement the helpers in `agent.py`**

**3a.** Replace `_list_problem`, `_employee_problem`, `_project_problem`, `_tim_problem` (current lines 45-136) with:

```python
def _missing_names(values: Sequence[str], valid: Sequence[str]) -> list[str]:
    """Values with no trim+case-insensitive match in `valid` (order kept)."""
    canonical = _canonical_map(valid)
    return [value for value in values if value.strip().casefold() not in canonical]


def _resolve_name(value: str, tool_name: str, valid: Sequence[str]) -> str:
    """Tool result for one find_* call: match text only, never a user question.

    The model decides what to ask the user after reading this (FR-09).
    """
    kind = "project" if tool_name == "find_project" else "employee"
    if not valid:
        return f"The {kind} list is unavailable, try again later."
    if not value:
        return 'Could not read the name. Call again with {"name": "..."} as plain text.'
    canonical = _canonical_map(valid)
    wanted = value.strip().casefold()
    if wanted in canonical:
        return f"Matched: {canonical[wanted]}"
    candidates = difflib.get_close_matches(value, list(canonical.values()), n=3, cutoff=0.5)
    if candidates:
        return (
            f'No exact match for "{value}". Closest: {", ".join(candidates)}. '
            "Ask the user which one is meant."
        )
    return f'"{value}" not found in the {kind} list. Ask the user to check the spelling.'


def _redirect_problems(
    calls: list[dict[str, Any]], employees: Sequence[str], projects: Sequence[str]
) -> dict[str, str]:
    """Per call id: the tool error that sends unresolved names back to find_*.

    Empty string for a call whose names are all in the lists. Runs only after
    FR-05 passed, so the arguments parse as a JSON object here.
    """
    problems: dict[str, str] = {}
    for tc in calls:
        args = json.loads(tc["function"].get("arguments", ""))
        lines: list[str] = []
        for value in _missing_names([str(args.get("nama_karyawan", ""))], employees):
            lines.append(
                f'Karyawan "{value}" belum dipastikan. Panggil find_employee '
                "untuk menyelesaikannya, lalu kirim ulang create_alokasi."
            )
        for value in _missing_names([str(args.get("nama_proyek", ""))], projects):
            lines.append(
                f'Proyek "{value}" belum dipastikan. Panggil find_project '
                "untuk menyelesaikannya, lalu kirim ulang create_alokasi."
            )
        tim = str(args.get("tim_pekerjaan") or "")
        members = [part.strip() for part in tim.split(",") if part.strip()]
        for value in _missing_names(members, employees):
            lines.append(
                f'Anggota tim "{value}" belum dipastikan. Panggil find_employee '
                "untuk menyelesaikannya, atau minta user menghapusnya dari tim."
            )
        problems[tc.get("id", "")] = " ".join(lines)
    return problems
```

**3b.** Add near the top of `agent.py` (after the imports):

```python
MAX_ROUNDS = 6
```

**3c.** Add the find-call extractor after `_alokasi_calls`:

```python
def _find_calls(message: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(tool_call id, function name, name) for every find_* call in the reply."""
    found: list[tuple[str, str, str]] = []
    for tc in message.get("tool_calls") or []:
        function = tc.get("function") or {}
        if function.get("name") not in ("find_employee", "find_project"):
            continue
        try:
            raw = json.loads(function.get("arguments") or "")
        except json.JSONDecodeError:
            raw = {}
        value = str(raw.get("name", "")) if isinstance(raw, dict) else ""
        found.append((tc.get("id", ""), function["name"], value.strip()))
    return found
```

- [ ] **Step 4: Rewrite `run()` as the round loop**

Replace the whole `run()` function (current `agent.py:214-408`) with:

```python
def run(
    raw_message: str,
    *,
    user_name: str,
    employees: Sequence[str],
    projects: Sequence[str],
    history: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
    now: datetime | None = None,
    complete: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Send one user message to the LLM and return (envelope dict, new history).

    `complete` is an injectable function `(messages, tools) -> dict` so tests
    can pass a stub; by default it is llm.complete.

    Bounded round loop: find_* calls get match results, create_alokasi calls
    get FR-05 validation, one row-guard nudge, and up to 2 redirects back to
    find_* for unresolved names. MAX_ROUNDS total, refusal when exhausted.
    """
    complete = complete or default_complete
    system = build_system_prompt(now or datetime.now(timezone.utc), user_name)
    prior = list(history or [])
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        *prior,
        {"role": "user", "content": raw_message},
    ]
    tools = to_openai_tools(CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL)
    confirmed = _confirmed_rows(prior)

    validation_retries = 0
    redirects = 0
    nudged = False
    refuse_reason = ""
    message: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    for _ in range(MAX_ROUNDS):
        response = complete(messages, tools=tools)
        message = response["choices"][0]["message"]

        finds = _find_calls(message)
        if finds:
            # Every tool call id in this turn gets a reply: find_* carries the
            # match result, a create_alokasi riding along gets "OK" and is only
            # acted on if the model sends it again in a later round.
            results = {
                fid: _resolve_name(
                    name, tool, employees if tool == "find_employee" else projects
                )
                for fid, tool, name in finds
            }
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": results.get(tc.get("id", ""), "OK"),
                    }
                    for tc in message.get("tool_calls") or []
                ],
            ]
            continue

        calls = _alokasi_calls(message)
        errors_by_id = _validate_calls(calls)

        if any(errors_by_id.values()):
            # FR-05: retry once, handing the validation errors back to the model.
            if validation_retries >= 1:
                errors = [
                    error
                    for tc in calls
                    for error in errors_by_id.get(tc.get("id", ""), [])
                ]
                refuse_reason = (
                    "Data tidak valid setelah dicoba ulang: " + "; ".join(errors)
                )
                break
            validation_retries += 1
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": "\n".join(errors_by_id.get(tc.get("id", ""), []))
                        or "OK",
                    }
                    for tc in message.get("tool_calls") or []
                ],
            ]
            continue

        if not calls:
            break  # plain text reply (or only unknown tool names) -> text envelope

        if missing := _missing_lists_message(employees, projects):
            # Fail-closed: with no list to check against, nothing reaches the ERP.
            refuse_reason = missing
            break

        if confirmed and not _same_rows(calls, confirmed):
            # FR-08 row guard: nudge once with the confirmed rows, refuse after.
            if nudged:
                refuse_reason = (
                    f"Isi alokasi tidak sesuai konfirmasi ({len(calls)} panggilan vs "
                    f"{len(confirmed)} baris, atau nilainya berbeda). "
                    "Tidak ada data yang dikirim."
                )
                break
            nudged = True
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": "OK",
                    }
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
            continue

        problems = _redirect_problems(calls, employees, projects)
        if any(problems.values()):
            # Fail closed: unresolved names go back to the model as a redirect
            # to find_* instead of a user-facing question (max 2 rounds).
            if redirects >= 2:
                refuse_reason = (
                    "Nama belum dapat dipastikan setelah beberapa percobaan. "
                    "Tidak ada data yang dikirim."
                )
                break
            redirects += 1
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": problems.get(tc.get("id", ""), "") or "OK",
                    }
                    for tc in message.get("tool_calls") or []
                ],
            ]
            continue

        # Accept: one row keeps the model's object string (PRD sample shape
        # unchanged); several rows become a JSON array string (FR-08). Names
        # are rewritten to the exact list spellings first.
        rows = [
            _canonicalize_row(tc["function"]["arguments"], employees, projects)
            for tc in calls
        ]
        arguments = (
            rows[0] if len(rows) == 1 else json.dumps([json.loads(row) for row in rows])
        )
        envelope = {
            "success": True,
            "type": "function_call",
            "function_name": "create_alokasi",
            "arguments": arguments,
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": message.get("content"),
        }
        history_content = message.get("content") or ""
        new_history = [
            *prior,
            {"role": "user", "content": raw_message},
            {"role": "assistant", "content": history_content},
        ]
        envelope["history"] = new_history
        return envelope, new_history
    else:
        # Loop used up MAX_ROUNDS without a decision (e.g. the model keeps
        # calling find_* without ever emitting create_alokasi).
        if not refuse_reason:
            refuse_reason = (
                "Percobaan terlalu banyak tanpa hasil. Tidak ada data yang dikirim."
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
    else:
        envelope = {
            "success": True,
            "type": "text",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": message.get("content"),
        }
        history_content = message.get("content") or ""

    new_history = [
        *prior,
        {"role": "user", "content": raw_message},
        {"role": "assistant", "content": history_content},
    ]
    # FR-16: the backend only sees the envelope, so the notepad rides along
    # in it; it stores the list and passes it back as history= next request.
    envelope["history"] = new_history
    return envelope, new_history
```

**3d.** Update the import line in `agent.py`:

```python
from alokasi_agent.schema import CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL, validate_arguments
```

(keep it under one line or split with parentheses, matching file style)

**3e.** Remove the now-unused helpers if Step 3a did not already: confirm `_list_problem`, `_employee_problem`, `_project_problem`, `_tim_problem` are gone.

- [ ] **Step 5: Verify no stale references**

Run: `.venv\Scripts\python.exe -m pytest tests\test_agent.py -q`
Expected: PASS (all old kept tests + all new/rewritten tests).

Run: `Select-String -Path src\alokasi_agent\*.py, tests\*.py -Pattern "_list_problem|_employee_problem|_project_problem|_tim_problem"`
Expected: no matches.

- [ ] **Step 6: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest --ignore=tests\test_main_chat.py -q`
Expected: PASS (0 failed).

---

### Task 5: Documentation (integration guide + FRD notes)

**Files:**
- Modify: `docs/integration-guide.md` (two spots, ~lines 146-148 and ~202-205)
- Modify: `PRD_FRD_create_alokasi_agent.md` (FR-02 delivered note; FR-09 new delivered note)

**Interfaces:**
- Consumes: final behavior from Tasks 1-4.
- Produces: docs that match the shipped contract.

- [ ] **Step 1: Update the caller contract in `integration-guide.md`**

Replace:

```
2. Send `employees` and `projects` on **every** request. The AI side performs
   no database lookups (PRD boundary §6) — it can only check names against the
   lists you send.
```

with:

```
2. Send `employees` and `projects` on **every** request. The AI side performs
   no database lookups (PRD boundary §6) — those lists are the source the
   `find_employee` / `find_project` tools match names against, so without them
   no name can be resolved.
```

(If your editor shows `§6` differently, match on the surrounding text `PRD boundary` + `lists you send`.)

- [ ] **Step 2: Update the "names are checked by the model" bullet**

Replace:

```
- **Names are checked by the model, not by code.** `validate_arguments()`
  checks *formats* (dates, times, non-empty). Whether `"Imam Ihsani"` really
  exists depends on the `employees` list you sent — which is why you must send
  it every turn.
```

with:

```
- **Names are resolved through tools, then checked by code.** The model never
  sees the full lists: it calls `find_employee` / `find_project`, which match
  the typed name against the `employees`/`projects` you sent (difflib), and
  only the returned spelling enters `create_alokasi`. A name that skips the
  tools is rejected with a redirect back to them. Which is why you must send
  both lists every turn.
```

- [ ] **Step 3: Amend the FR-02 delivered note**

In `PRD_FRD_create_alokasi_agent.md` (FR-02 section), replace:

```
(`PROMPT_TEMPLATE` + `build_system_prompt(now, user_name, employees, projects)`). **Injected-context contract:** the caller supplies `user_name`, `employee_list`, `project_list` per request — this repo performs no DB lookups (boundary §6); WIB time is derived from `now`, rendered `Rabu, 30 September 2026, 14:05 WIB`.
```

with:

```
(`PROMPT_TEMPLATE` + `build_system_prompt(now, user_name)`). **Injected-context contract (amended 2026-10-16):** only `user_name` and the WIB time are injected — the employee/project lists are never put in the prompt; the caller passes `employees`/`projects` to `run()` and the model resolves names through the `find_employee`/`find_project` tools (FR-09). This repo performs no DB lookups (boundary §6); WIB time is derived from `now`, rendered `Rabu, 30 September 2026, 14:05 WIB`.
```

(Match on the actual file text — it may contain `§` or an em dash variant; keep whatever character is already there.)

- [ ] **Step 4: Add the FR-09 delivered note**

In the FR-09 section, after the `**Done when:**` line, append:

```
> **Delivered (2026-10-16).** Entity resolution runs through the `find_employee` / `find_project` tools (`src/alokasi_agent/schema.py`) with `difflib` matching against the caller-supplied lists (`_resolve_name` in `src/alokasi_agent/agent.py`): exact match → canonical spelling returned to the model, near-match → up to 3 candidates, no match → "not found". A `create_alokasi` call containing a name that never went through the tools is redirected back to them (`_redirect_problems`, max 2 rounds, then a refusal). The model phrases the user-facing question ("Maksud kamu Imam Ihsani?") after reading the tool result. Pinned by the `test_resolve_name_*` and redirect tests in `tests/test_agent.py`.
```

- [ ] **Step 5: Verify docs render sanely**

Run: `Select-String -Path docs\integration-guide.md, PRD_FRD_create_alokasi_agent.md -Pattern "find_employee"`
Expected: matches in both files.

---

### Task 6: Verification (pytest, live smoke, eval baseline)

**Files:**
- No source changes expected; `eval/baseline.json` refresh only if metrics shifted.

**Interfaces:**
- Consumes: Tasks 1-5 complete.

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest --ignore=tests\test_main_chat.py -q`
Expected: PASS (0 failed, 0 errors).

- [ ] **Step 2: Live FR-04 smoke (requires `OPENAI_API_KEY`)**

Run: `.venv\Scripts\python.exe scripts\smoke_agent.py`
Expected: exit 0 (arguments equal the PRD sample). The model must now do a `find_*` round before `create_alokasi` — `run()` handles that internally.

If `OPENAI_API_KEY` is not set: report "live checks skipped (no key)" to the user; do not fake it.

- [ ] **Step 3: Live eval run + baseline refresh**

Run: `.venv\Scripts\python.exe scripts\run_eval.py`
Expected: report printed; compare per-case deltas. If the results are acceptable (score holds, token counts dropped for prompt input), refresh the baseline:

Run: `.venv\Scripts\python.exe scripts\run_eval.py --update-baseline`
Expected: `updated eval/baseline.json`.

If score regressions appear: report the failing case ids to the user before touching the baseline — do not update it blindly.

- [ ] **Step 4: Report**

Summarize for the user: suite result, smoke result, eval headline (score + token delta vs baseline), and whether the baseline was updated.
