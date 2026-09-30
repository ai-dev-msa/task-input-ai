# FR-02 Slice A: LLM Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A thin sync OpenAI client with env-driven config and an adapter that feeds our provider-neutral `CREATE_ALOKASI_TOOL` contract to the API.

**Architecture:** `llm.py` holds a frozen `LLMConfig` (single place for model/temperature/timeout/key), an `LLMClient` wrapping `openai.OpenAI` with one `complete()` method returning the raw `ChatCompletion`, and `to_openai_tools()` — the only provider-specific translation in the codebase. Parsing and routing stay out (FR-04).

**Tech Stack:** Python 3.14 venv (`.venv`), `openai>=1.40`, Pydantic v2, pytest.

## Global Constraints

- Defaults: `model="gpt-4o-mini"`, `temperature=0.0`, `timeout=30.0`
- `OPENAI_API_KEY` required — fail fast with a clear message; `OPENAI_BASE_URL`, `ALOKASI_MODEL`, `ALOKASI_TEMPERATURE`, `ALOKASI_TIMEOUT` optional overrides
- `complete()` returns the raw SDK `ChatCompletion`; SDK errors propagate unwrapped (no catch/retry/mapping)
- Tool conversion: `{name, description, input_schema}` → `[{"type": "function", "function": {name, description, parameters}}]`
- **No network calls in tests** — user tests the client manually via `scripts/smoke_llm.py`
- Out of scope: system prompt, WIB date injection, tool-call-vs-text routing, envelope building, error mapping
- All commands run from repo root `C:\Users\ACER\Documents\GitHub\task-input-ai`; shell is PowerShell 5.1 (never `>`-redirect Python output)
- Tests: `.venv\Scripts\python.exe -m pytest ...`
- Commits to `dev` pre-authorized: exact messages below, no push, no amend; never stage `.superpowers/`, `docs/`, `__pycache__`, `*.egg-info`, `.venv`

---

### Task 1: Dependency, `llm.py`, and pure-function tests

**Files:**
- Modify: `pyproject.toml`
- Create: `src/alokasi_agent/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: `CREATE_ALOKASI_TOOL` from `alokasi_agent.schema` (Task 1 of FR-01: keys `name`, `description`, `input_schema`).
- Produces: `LLMConfig` (frozen dataclass, `LLMConfig.from_env() -> LLMConfig`), `LLMClient(config: LLMConfig | None = None)` with `complete(messages: list[dict], tools: list[dict] | None = None) -> ChatCompletion`, `to_openai_tools(tool: dict) -> list[dict]`. Slice B and FR-04 import these exact names.

- [ ] **Step 1: Add the dependency and install**

Edit `pyproject.toml` — change line 10 from:
```toml
dependencies = ["pydantic>=2.7,<3"]
```
to:
```toml
dependencies = ["pydantic>=2.7,<3", "openai>=1.40"]
```

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected: `Successfully installed openai-...`.

- [ ] **Step 2: Write the failing tests** — create `tests/test_llm.py`:

```python
import pytest

from alokasi_agent.llm import LLMClient, LLMConfig, to_openai_tools
from alokasi_agent.schema import CREATE_ALOKASI_TOOL

OVERRIDE_VARS = (
    "ALOKASI_MODEL",
    "ALOKASI_TEMPERATURE",
    "ALOKASI_TIMEOUT",
    "OPENAI_BASE_URL",
)


def _clear_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for var in OVERRIDE_VARS:
        monkeypatch.delenv(var, raising=False)


def test_from_env_requires_api_key(monkeypatch):
    _clear_env(monkeypatch)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMConfig.from_env()


def test_from_env_defaults_when_only_key_set(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = LLMConfig.from_env()
    assert cfg.api_key == "sk-test"
    assert cfg.model == "gpt-4o-mini"
    assert cfg.temperature == 0.0
    assert cfg.timeout == 30.0
    assert cfg.base_url is None


def test_from_env_applies_overrides(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_MODEL", "gpt-4o-mini-2024-07-18")
    monkeypatch.setenv("ALOKASI_TEMPERATURE", "0.2")
    monkeypatch.setenv("ALOKASI_TIMEOUT", "12.5")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")
    cfg = LLMConfig.from_env()
    assert cfg.model == "gpt-4o-mini-2024-07-18"
    assert cfg.temperature == 0.2
    assert cfg.timeout == 12.5
    assert cfg.base_url == "https://proxy.example/v1"


def test_from_env_rejects_non_numeric_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_TIMEOUT", "cepat")
    with pytest.raises(ValueError, match="ALOKASI_TIMEOUT"):
        LLMConfig.from_env()


def test_to_openai_tools_converts_provider_neutral_contract():
    tools = to_openai_tools(CREATE_ALOKASI_TOOL)
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    function = tools[0]["function"]
    assert function["name"] == "create_alokasi"
    assert function["description"] == CREATE_ALOKASI_TOOL["description"]
    assert function["parameters"] == CREATE_ALOKASI_TOOL["input_schema"]


def test_client_keeps_injected_config():
    cfg = LLMConfig(api_key="sk-test", model="test-model", temperature=0.7, timeout=5.0)
    client = LLMClient(cfg)
    assert client.config is cfg
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_llm.py -v
```

Expected: `ImportError: cannot import name 'LLMConfig' from 'alokasi_agent.llm'` (module missing).

- [ ] **Step 4: Implement `src/alokasi_agent/llm.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    timeout: float = 30.0
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> LLMConfig:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Export it before creating an LLMClient."
            )
        return cls(
            api_key=api_key,
            model=os.environ.get("ALOKASI_MODEL") or cls.model,
            temperature=_env_float("ALOKASI_TEMPERATURE", cls.temperature),
            timeout=_env_float("ALOKASI_TIMEOUT", cls.timeout),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if tools:
            kwargs["tools"] = tools
        return self._client.chat.completions.create(**kwargs)


def to_openai_tools(tool: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
    ]
```

- [ ] **Step 5: Run the full suite**

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: 24 existing + 6 new = 30 passed, pristine output.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml src tests
git commit -m "feat(fr-02): add LLM client with env config and openai tool adapter"
```

---

### Task 2: Manual smoke-test harness

**Files:**
- Create: `scripts/smoke_llm.py`

**Interfaces:**
- Consumes: `LLMClient`, `to_openai_tools` (Task 1), `CREATE_ALOKASI_TOOL` (FR-01).
- Produces: a runnable script — `.venv\Scripts\python.exe scripts\smoke_llm.py [--dry-run]`. This is the user's manual verification path; no automated test file for it.

- [ ] **Step 1: Create `scripts/smoke_llm.py`**

```python
"""Manual smoke test for the FR-02 LLM client. Run: scripts/smoke_llm.py [--dry-run]"""

from __future__ import annotations

import argparse
import json
import sys

from alokasi_agent.llm import LLMClient, to_openai_tools
from alokasi_agent.schema import CREATE_ALOKASI_TOOL

EXAMPLE_MESSAGE = (
    "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan "
    "Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026"
)


def build_request() -> tuple[list[dict], list[dict]]:
    messages = [{"role": "user", "content": EXAMPLE_MESSAGE}]
    return messages, to_openai_tools(CREATE_ALOKASI_TOOL)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the FR-02 LLM client")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the request payload without calling the API (no key needed)",
    )
    args = parser.parse_args()

    messages, tools = build_request()

    if args.dry_run:
        print(json.dumps({"messages": messages, "tools": tools}, indent=2, ensure_ascii=False))
        return 0

    client = LLMClient()
    response = client.complete(messages, tools=tools)
    message = response.choices[0].message

    if message.tool_calls:
        for call in message.tool_calls:
            print(f"tool call: {call.function.name}")
            print(json.dumps(json.loads(call.function.arguments), indent=2, ensure_ascii=False))
    else:
        print("text reply (no tool call):")
        print(message.content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: there is no system prompt yet (Slice B), so a plain-text reply is an acceptable outcome for this slice — the run proves auth, tool serialization, and round-trip wiring. The "returns a `create_alokasi` tool call" done-condition belongs to Slice B.

- [ ] **Step 2: Verify dry-run wiring (no API key needed)**

```powershell
.venv\Scripts\python.exe scripts\smoke_llm.py --dry-run
```

Expected: JSON with the FRD §6 example message and the converted OpenAI tool (type `function`, parameters = our input_schema).

- [ ] **Step 3: Run the full suite to confirm nothing broke**

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: 30 passed.

- [ ] **Step 4: Commit**

```powershell
git add scripts
git commit -m "feat(fr-02): add LLM smoke-test harness"
```

---

## Done criteria (FR-02 Slice A)

`.venv\Scripts\python.exe scripts\smoke_llm.py` with `OPENAI_API_KEY` set performs a live round-trip; `--dry-run` proves the wiring without a key. Slice B (system prompt + WIB injection + guaranteed tool call) starts from `LLMClient.complete()` unchanged.
