# Jam Selesai Ask Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the model from ever reaching the user with a question about the optional `jam_selesai` when the user simply omitted the end time, by adding a prompt example (A) and a one-shot in-loop guard (B).

**Architecture:** One negative example is added to `PROMPT_TEMPLATE`'s `# Examples`. In `agent.py`, a plain detector `_asks_about_jam_selesai()` notices when a plain-text reply asks about jam selesai; `run()` then appends one conditional reminder message and loops once (same bounded-retry shape as the existing FR-05 validation retry and FR-08 row-guard nudge). If the model still asks, the second ask is returned — a deterrent, not a hard gate.

**Tech Stack:** Python, stdlib only, pytest.

**Spec:** Design approved in session (2026-11-02): approaches A (prompt example) + B (loop guard) chosen over C (hard gate, rejected — would require parsing times out of raw messages in Python). Reproduced failure: user message *"isikan alokasi untuk saya, testing chatbot, proyek OPRS Divisi WIN 2026 dari jam 9"* (start given, no date, no end) → reply *"Jam selesai berapa dan tanggalnya kapan?"* — the question must cover `tanggal` only.

## Global Constraints

- Plain functions, no classes, no new abstractions or layers (AGENTS.md).
- Simplest solution that works; minimal changes; no unrelated refactors.
- Prefer editing existing files; no new files needed for this plan.
- No new dependencies; stdlib only.
- Do not commit unless explicitly asked (AGENTS.md) — this plan has no commit steps.
- Tests: `.venv\Scripts\python.exe -m pytest`
- Leave items marked TBD in PRD/FRD open; implement only this guard.

## Review Focus

- **Legitimate jam selesai ask survives** (user wrote an end time that is invalid or ambiguous, e.g. overnight): the nudge is conditional, so the model re-asks and that ask is returned — pinned by `test_guard_returns_second_ask_without_looping`.
- **Detector false positive on confirmations**: a summary line ending `Benar?` never contains the words "jam selesai" — pinned in `test_asks_about_jam_selesai_detects_questions_only`.
- **Empty model reply** (`content=None`) must not crash the detector — pinned in the same detector test.
- **Nudge leaking to the frontend**: history is rebuilt from `raw_message` + final content, so the nudge round never appears — pinned by the history-role assert in `test_guard_nudges_then_returns_corrected_reply`.
- **Loop bounded**: `ask_nudged` flag allows at most one guard round — pinned by the `len(calls) == 2` asserts in both guard tests.

---

### Task 1: Negative prompt example (approach A)

**Files:**
- Modify: `src/alokasi_agent/prompt.py` — `# Examples` section, insert directly after the "nulis draft SOP pengadaan" example (ends line 165).
- Test: `tests/test_prompt.py` — extend `test_missing_optional_end_time_never_prompts_ask` (line 135).

**Interfaces:**
- Produces: the example line `"Tanggal alokasinya kapan?"` inside `PROMPT_TEMPLATE`, which the test asserts on.

- [ ] **Step 1: Add the failing assert to the existing test**

In `tests/test_prompt.py`, inside `test_missing_optional_end_time_never_prompts_ask`, after the existing asserts (line 146), add:

```python
    # Example: date missing but the start given — the ask covers tanggal only.
    assert "Tanggal alokasinya kapan?" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompt.py::test_missing_optional_end_time_never_prompts_ask -v`
Expected: FAIL with `AssertionError: assert 'Tanggal alokasinya kapan?' in ...`

- [ ] **Step 3: Insert the example into `PROMPT_TEMPLATE`**

In `src/alokasi_agent/prompt.py`, directly after the "nulis draft SOP pengadaan" example block (after line 165), insert:

```
"isikan alokasi untuk saya, revisi modul PPN, proyek OPRS Divisi WIN 2026 dari jam 9"
-> "Tanggal alokasinya kapan?"   (start given, no date: the question covers only the
   missing required field; the omitted end time is never added to it)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompt.py -v`
Expected: all PASS

---

### Task 2: One-shot guard in the loop (approach B)

**Files:**
- Modify: `src/alokasi_agent/agent.py` — new constant next to `MAX_ROUNDS` (line 20), new helper with the other `_`-prefixed helpers, flag init next to `nudged = False` (line 253), guard at `if not calls:` (line 324).
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `make_stub(replies, calls)` and `text_reply(content)` test helpers (already in `tests/test_agent.py`); add `_asks_about_jam_selesai` to the existing `from alokasi_agent.agent import _find_calls, _resolve_name` import (line 5).
- Produces: `_asks_about_jam_selesai(reply: str | None) -> bool`; module constant `_ASK_NUDGE: str`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_agent.py`: first add `_asks_about_jam_selesai` to the existing import on line 5 (`from alokasi_agent.agent import _find_calls, _resolve_name`), then add:

```python
GUARD_ASK = "Jam selesai berapa dan tanggalnya kapan?"
GUARD_OK = "Tanggal alokasinya kapan?"


def test_asks_about_jam_selesai_detects_questions_only():
    assert _asks_about_jam_selesai(GUARD_ASK) is True
    assert _asks_about_jam_selesai("Jam_selesai nya berapa?") is True
    assert _asks_about_jam_selesai(GUARD_OK) is False
    assert _asks_about_jam_selesai("Budi | OPRS | 2026-11-02 | task | 09:00. Benar?") is False
    assert _asks_about_jam_selesai(None) is False


def test_guard_nudges_then_returns_corrected_reply():
    calls = []
    stub = make_stub([text_reply(GUARD_ASK), text_reply(GUARD_OK)], calls)
    env, history = call_run(stub)
    assert env["reply"] == GUARD_OK
    assert len(calls) == 2
    assert calls[1]["messages"][-1]["role"] == "user"
    assert "Jam_selesai opsional" in calls[1]["messages"][-1]["content"]
    # the nudge round never leaks into the history the frontend sees
    assert [t["role"] for t in history] == ["user", "assistant"]
    assert history[1]["content"] == GUARD_OK


def test_guard_returns_second_ask_without_looping():
    calls = []
    stub = make_stub([text_reply(GUARD_ASK), text_reply(GUARD_ASK)], calls)
    env, _ = call_run(stub)
    assert env["reply"] == GUARD_ASK
    assert len(calls) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_agent.py -k "guard or asks_about" -v`
Expected: FAIL at collection with `ImportError: cannot import name '_asks_about_jam_selesai'`

- [ ] **Step 3: Implement the guard in `src/alokasi_agent/agent.py`**

1. After `MAX_ROUNDS = 6` (line 20), add the nudge constant (exact text — the test asserts on `"jam_selesai opsional"`):

```python
_ASK_NUDGE = (
    "Jam_selesai opsional. Jangan ditanyakan bila user tidak menulis waktu "
    "berakhirnya; tanyakan hanya field wajib yang kosong. Tanyakan jam selesai "
    "hanya bila user sudah menulis waktunya tapi ambigu atau tidak valid. Jawab ulang."
)
```

2. With the other module-level helpers, add:

```python
def _asks_about_jam_selesai(reply: str | None) -> bool:
    """True when a reply is a question that mentions the optional end time."""
    text = (reply or "").lower().replace("_", " ")
    return "?" in text and "jam selesai" in text
```

3. Next to `nudged = False` (line 253), add `ask_nudged = False`.
4. Replace the `if not calls:` exit (line 324):

```python
        if not calls:
            if not ask_nudged and _asks_about_jam_selesai(message.get("content")):
                # One conditional reminder: the model re-reads its own question
                # and keeps it only if the user really wrote an end time.
                ask_nudged = True
                messages = messages + [
                    {"role": "assistant", "content": message.get("content")},
                    {"role": "user", "content": _ASK_NUDGE},
                ]
                continue
            break  # plain text reply (or only unknown tool names) -> text envelope
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_agent.py -k "guard or asks_about" -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: all PASS
