# Project Fetch + List Validation + Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/chat` sources its project list from the server's existing `modules.proyek` controller (cached, TTL), hard-validates every `create_alokasi` row's `nama_proyek` against it (answering `Maksud kamu "X"?` instead of calling CI3), and orders the prompt so OpenAI's prefix cache can serve the stable block.

**Architecture:** Three small layers: (1) `main.py` gains a module-level TTL cache + `get_projects()` wrapping the already-deployed `ProyekController`; (2) `src/alokasi_agent/agent.py` gains a post-FR-05 list check that turns any unknown project into a `type: "text"` envelope (which `main.py` already never POSTs); (3) `prompt.py` placeholder block moves below the static text so the cached prefix stays byte-stable.

**Tech Stack:** Flask + flask-cors + requests (main.py), OpenAI via `alokasi_agent` package, stdlib only for new code (`time`, `difflib`, `zoneinfo`), pytest for tests.

## Global Constraints

- Plain functions, no classes, no new third-party dependencies (AGENTS.md)
- Tests run: `.venv\Scripts\python.exe -m pytest`
- One commit per task on the `dev` branch (user-approved for this run)
- Envelope contract unchanged: the question reuses `type: "text"`, `success: true`
- Employees stay prompt-only: no fetching, no code validation of `nama_karyawan`/`tim_pekerjaan`
- `modules.proyek` exists only on the server — `main.py` cannot be imported locally; verify it with `py_compile` + server smoke
- Cache TTL: `ALOKASI_CACHE_TTL` seconds, default `300`, used for both `projects` and `erp_token`
- Projects: fetch wins; request-body `projects` only as fallback when fetch yields nothing
- Keep it simple per AGENTS.md: simplest solution that works, no unasked-for features or error handling

---

### Task 1: Save design spec document

**Files:**
- Create: `docs/superpowers/specs/2026-10-07-project-fetch-validation-cache-design.md`

**Interfaces:**
- Consumes: the design below (approved by the user in conversation)
- Produces: written spec at the path above; user reviews it before code tasks start

- [ ] **Step 1: Write the spec doc** containing exactly this approved design:

```markdown
# Project fetch + list validation + caching (2026-10-07)

## Data flow
POST /chat
  -> get_projects()            [new, main.py]
       cache hit (TTL 300s) -> merged names
       miss -> get_erp_token() (cached) -> controller.getProyekMSAByYear
                                       + controller.getProyekWINByYear (tahun = WIB now)
                                       -> normalize -> merge/dedupe -> cache
       any failure -> body projects -> []
  -> employees = body employees (prompt-only; no code validation)
  -> run() -> prompt: static -> lists -> time/user -> OpenAI (prefix cache)
  -> model returns create_alokasi call(s)
  -> FR-05 format validation (existing, retry once)
  -> NEW: nama_proyek vs fetched list (trim + case-insensitive)
       miss  -> envelope type "text": Maksud kamu "X"? Kandidat: A, B, C
                no function_call -> main.py never calls get_erp_token / POST
       pass  -> get_erp_token() (cached) -> POST each row to CI3 (existing)

## Decisions (user-approved)
- Source: import `controller` from modules.proyek (routes reuse; no HTTP hop)
- Routes: MSA + WIN both, tahun = current WIB year, merged, case-insensitive dedupe
- Employees: no employee list exists anywhere -> prompt rules only, body-supplied
- Match: trim + case-insensitive; unknown -> question + up to 3 difflib candidates
- Envelope: success true, type "text" for the question; batch blocked if any row bad
- Failure: fetch fails -> body projects -> []; never break /chat because MIS is down
- Cache: one TTL (ALOKASI_CACHE_TTL, default 300s) for lists and token
- Prompt order: static text -> lists -> time/user (OpenAI prefix cache)
- Validation lives in the package (pytest-covered), not main.py
```

- [ ] **Step 2: Commit the spec doc**

```bash
git add docs/superpowers/specs/2026-10-07-project-fetch-validation-cache-design.md
git commit -m "docs: spec for project fetch, list validation, caching"
```

- [ ] **Step 3: Ask the user to review the spec** before continuing to Task 2.

---

### Task 2: Package — project list check turns unknown projects into a question

**Files:**
- Modify: `src/alokasi_agent/agent.py:88` (envelope chain) + imports
- Test: `tests/test_agent.py` (new section at end of file)

**Interfaces:**
- Consumes: `run(..., projects=...)` (existing signature, unchanged)
- Produces: internal `_project_problem(calls, projects) -> str | None` in `agent.py`; behavior contract used by Task 4: unknown project ⇒ envelope `{"success": true, "type": "text", ...}` with `reply` starting `Maksud kamu "..."?`, exactly 1 `complete()` call (no retry)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_agent.py`:

```python
# --- project list validation (server-fetched lists) ---

def test_unknown_project_becomes_question_not_call():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "OPRS WIN")
    calls = []
    env, history = call_run(make_stub([tool_reply(arguments=args)], calls))
    assert env["success"] is True
    assert env["type"] == "text"
    assert env["function_name"] == ""
    assert env["arguments"] == ""
    assert 'Maksud kamu "OPRS WIN"?' in env["reply"]
    assert "OPRS Divisi WIN 2026" in env["reply"]
    assert len(calls) == 1  # list misses are not retried
    assert history[-1]["content"] == env["reply"]


def test_unknown_project_blocks_whole_batch():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "Proyek Fiktif")
    calls = []
    env, _ = call_run(make_stub([tool_reply_multi([SAMPLE_ARGUMENTS, bad])], calls))
    assert env["type"] == "text"
    assert 'Maksud kamu "Proyek Fiktif"?' in env["reply"]
    assert len(calls) == 1


def test_project_match_ignores_case_and_padding():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "  oprs divisi win 2026 ")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []))
    assert env["type"] == "function_call"


def test_empty_projects_list_skips_check():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "Anything At All")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []), projects=[])
    assert env["type"] == "function_call"


def test_no_close_candidate_still_asks():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "zzz qqq")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []))
    assert env["type"] == "text"
    assert 'Maksud kamu "zzz qqq"?' in env["reply"]
    assert "Kandidat:" not in env["reply"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\test_agent.py -k "project" -v`
Expected: FAIL — unknown projects still produce `type == "function_call"` (e.g. `assert "text" == "function_call"`).

- [ ] **Step 3: Implement** — in `src/alokasi_agent/agent.py`, add `import difflib` after `import json`, add this helper after `_validate_calls`, and insert one branch in `run()`:

```python
def _project_problem(
    calls: list[dict[str, Any]], projects: Sequence[str]
) -> str | None:
    """Hard list check: every row's nama_proyek must exist in `projects`.

    Trim + case-insensitive match. Returns the user-facing question when some
    row's project is unknown, else None. Empty list means "no list to check
    against", so the check is skipped.
    """
    if not projects:
        return None
    canonical: dict[str, str] = {}
    for name in projects:
        canonical.setdefault(name.strip().casefold(), name)
    lines: list[str] = []
    for tc in calls:
        args = json.loads(tc["function"].get("arguments", ""))
        value = str(args.get("nama_proyek", "")).strip()
        if value.casefold() in canonical:
            continue
        candidates = difflib.get_close_matches(
            value, list(canonical.values()), n=3, cutoff=0.6
        )
        if candidates:
            lines.append(
                f'Maksud kamu "{value}"? Kandidat: {", ".join(candidates)}'
            )
        else:
            lines.append(
                f'Maksud kamu "{value}"? Tidak ada proyek yang mirip di daftar proyek.'
            )
    return " ".join(lines) or None
```

In `run()`, compute `project_question` right before `if any(errors_by_id.values()):` (currently `agent.py:69`) and add the branch between the FR-05 refusal block (ending at line 103) and `elif calls:` (line 104), resulting chain:

```python
    project_question = _project_problem(calls, projects) if calls else None

    if any(errors_by_id.values()):
        # ... existing FR-05 refusal block, unchanged ...
        ...
    elif project_question:
        # List miss: ask instead of writing (never a function_call).
        envelope = {
            "success": True,
            "type": "text",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": project_question,
        }
        history_content = project_question
    elif calls:
        # ... existing function_call block, unchanged ...
```

- [ ] **Step 4: Run the new tests**

Run: `.venv\Scripts\python.exe -m pytest tests\test_agent.py -v`
Expected: all PASS, including the 21 pre-existing tests (all existing rows use `"OPRS Divisi WIN 2026"` which is in `PROJECTS`).

- [ ] **Step 5: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/alokasi_agent/agent.py tests/test_agent.py
git commit -m "feat: block unknown projects with a Maksud kamu question (FR-09)"
```

---

### Task 3: Prompt reorder — lists before time/user

**Files:**
- Modify: `src/alokasi_agent/prompt.py:34-37` (move) and `:39-48` (anchor)
- Test: `tests/test_prompt.py`

**Interfaces:**
- Consumes: `PROMPT_TEMPLATE` placeholders (all four names unchanged)
- Produces: rendered order `static intro -> "Why this matters"/"Success means" -> Valid employees -> Valid projects -> Current date and time -> Logged-in user -> "# Instructions"...`

- [ ] **Step 1: Write the failing test** — append to `tests/test_prompt.py`:

```python
def test_static_and_lists_precede_volatile_values():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert out.index("Success means:") < out.index("Valid employees:")
    assert out.index("Valid employees:") < out.index("Current date and time")
    assert out.index("Valid projects:") < out.index("Logged-in user:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests\test_prompt.py::test_static_and_lists_precede_volatile_values -v`
Expected: FAIL with `ValueError: substring not found` (no `Success means:` before lists — currently the time block sits first).

- [ ] **Step 3: Reorder `PROMPT_TEMPLATE`**

Delete these 4 lines from their current spot (currently lines 34-37, right after the intro paragraph):

```
Current date and time (WIB, UTC+7): {{now_wib}}
Logged-in user: {{current_user_name}}
Valid employees: {{employee_list}}
Valid projects: {{project_list}}
```

Insert immediately after the paragraph ending `...as few words as possible.` (currently line 48) and before `# Instructions`:

```
Valid employees: {{employee_list}}
Valid projects: {{project_list}}

Current date and time (WIB, UTC+7): {{now_wib}}
Logged-in user: {{current_user_name}}
```

No other template text moves; all four `{{placeholders}}` stay identical.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests\test_prompt.py -v`
Expected: all PASS (existing tests use `in` assertions, unaffected).

- [ ] **Step 5: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/alokasi_agent/prompt.py tests/test_prompt.py
git commit -m "perf: put static text + lists before time/user for prefix caching"
```

---

### Task 4: `main.py` — TTL cache, `get_projects()`, cached `get_erp_token()`, `/chat` wiring

**Files:**
- Modify: `main.py:1-19` (imports), `main.py:87-94` (list sourcing), `main.py:181-233` (token cache), new functions after line 19
- Modify: `.env.example` (one line)

**Interfaces:**
- Consumes: `modules.proyek.controller` (module-level `ProyekController` instance; methods `getProyekMSAByYear(tahun, token) -> (Response, int)` and `getProyekWINByYear(tahun, token) -> (Response, int)`), existing `get_erp_token()`, `run(..., projects=...)`
- Produces: `get_projects() -> list[str]` (may be `[]` on failure); `get_erp_token() -> str` cached; cache helpers `_cache_get(key)`/`_cache_set(key, value)`; env `ALOKASI_CACHE_TTL`

- [ ] **Step 1: Update imports and register blueprint** — replace lines 1-19 of `main.py` with:

```python
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from alokasi_agent import run
import json
import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo



load_dotenv("/var/www/html/msaai/.env", override=True)

app = Flask(__name__)

import sys
sys.path.insert(0, "/var/www/html/msaai/ai-service/app")

from modules.proyek import proyek_bp, controller
app.register_blueprint(proyek_bp)
```

- [ ] **Step 2: Add the cache + fetch functions** — immediately after the blueprint registration:

```python
# Satu TTL untuk cache proyek & token ERP (detik).
CACHE_TTL = float(os.getenv("ALOKASI_CACHE_TTL", "300"))
_cache = {}


def _cache_get(key):
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[1]:
        return hit[0]
    return None


def _cache_set(key, value):
    _cache[key] = (value, time.monotonic() + CACHE_TTL)


def _names_from(data):
    """Ambil nama proyek dari response MIS: string dipakai apa adanya,
    dict dicoba lewat key nama yang umum, sisanya dilewati."""
    if isinstance(data, dict):
        data = data.get("data") or data.get("hasil") or []
    names = []
    for item in data or []:
        if isinstance(item, str) and item.strip():
            names.append(item)
        elif isinstance(item, dict):
            for key in ("nama", "name", "nama_proyek"):
                if item.get(key):
                    names.append(str(item[key]))
                    break
    return names


def get_projects():
    """Daftar proyek MSA+WIN tahun berjalan, digabung dan di-cache.
    Kalau gagal, kembalikan [] dan biarkan /chat pakai projects dari body."""
    cached = _cache_get("projects")
    if cached is not None:
        return cached
    names = []
    try:
        token = get_erp_token()
        tahun = str(datetime.now(ZoneInfo("Asia/Jakarta")).year)
        for fetch in (controller.getProyekMSAByYear, controller.getProyekWINByYear):
            response, status = fetch(tahun, token)
            if status == 200:
                names += _names_from(response.get_json().get("data"))
    except Exception as exc:
        print("get_projects gagal:", repr(exc))
    # Dedupe case-insensitive, urutan pertama dipertahankan.
    seen = set()
    merged = []
    for name in names:
        key = name.strip().casefold()
        if key not in seen:
            seen.add(key)
            merged.append(name.strip())
    _cache_set("projects", merged)
    return merged
```

- [ ] **Step 3: Wire `/chat`** — replace lines 87-94 with:

```python
        # Proyek dari endpoint server (cached); body hanya fallback.
        projects = get_projects() or (data.get("projects") or [])
        envelope, _history = run(
            user_message,
            user_name=data.get("user_name") or "",
            employees=data.get("employees") or [],
            projects=projects,
            history=data.get("history") or [],
            user_id=user_id,
        )
```

- [ ] **Step 4: Cache the token** — wrap `get_erp_token()` (defined at line 181):

```python
def get_erp_token():
    cached = _cache_get("erp_token")
    if cached is not None:
        return cached

    username = os.getenv("ERP_API_USERNAME")
    # ... entire existing body unchanged, then before `return token` add:

    _cache_set("erp_token", token)
    return token
```

(The proyek routes already call `main.get_erp_token()`, so they inherit the cache — no change to `modules.proyek`.)

- [ ] **Step 5: Document the env var** — append to `.env.example`:

```
ALOKASI_CACHE_TTL=300
```

- [ ] **Step 6: Syntax check + full suite**

Run: `.venv\Scripts\python.exe -m py_compile main.py` then `.venv\Scripts\python.exe -m pytest`
Expected: py_compile silent success; all tests PASS. (A real `import main` is impossible locally — `modules.proyek` lives only on the server.)

- [ ] **Step 7: Commit**

```bash
git add main.py .env.example
git commit -m "feat: server-side project fetch with TTL cache for lists and token"
```

---

### Task 5: Verification

**Files:** none modified

- [ ] **Step 1: Full suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: all PASS (should be 89+ tests).

- [ ] **Step 2: Live smoke (needs `OPENAI_API_KEY`)**

Run: `.venv\Scripts\python.exe scripts\smoke_agent.py`
Expected: existing behavior unchanged (fixture project is in `PROJECTS`, so the list check stays silent). If `OPENAI_API_KEY` is not set, report SKIPPED with the reason.

- [ ] **Step 3: Server checklist (manual, after deploy)** — report results:
  1. `GET /` returns health JSON (imports OK, `controller` import resolves).
  2. `POST /chat` with a message naming a real project → `type: "function_call"`, rows POSTed; second call within 5 min logs no new MIS fetch (`get_projects` cache).
  3. `POST /chat` with a bogus project name → `type: "text"`, `reply` starts `Maksud kamu "..."?`, **no** `hasil_ci3` key, ERP untouched.
  4. `GET /proyek/getProyekMSAByYear?tahun=2026` still works (routes untouched).
