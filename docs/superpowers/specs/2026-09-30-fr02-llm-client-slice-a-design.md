# FR-02 Slice A Design: LLM Client

Date: 2026-09-30
Source: `PRD_FRD_create_alokasi_agent.md` FR-02 (#2) — client portion only
Status: approved

## Goal

A thin, sync LLM client that FR-04's extraction pipeline calls: configuration in one place, one `complete()` method, the provider-neutral tool contract converted for OpenAI. Slice B (system prompt, WIB date injection, "never guess missing fields", live tool-call smoke) follows immediately after.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Structure | Approach A: thin wrapper module | One seam for config, one seam to mock/swap later; callers never touch SDK internals |
| Sync or async | Synchronous `openai.OpenAI` | FR-02..FR-04 are sequential; async would thread through every later FR for no gain (YAGNI) |
| Provider / endpoint | Standard OpenAI API, `gpt-4o-mini` default | User decision; model overridable via env |
| Temperature | `0.0` default | Deterministic extraction; PRD goal is precision, not variety |
| Timeout | `30.0` seconds default | User-tunable |
| API key | `OPENAI_API_KEY`, required, fail fast | Never hardcode; missing key must fail with a clear message at client construction, not at first call |
| Errors | SDK errors propagate unwrapped | Timeout/4xx/5xx mapping belongs to FR-11, not the client |
| Return value | Raw `ChatCompletion` | Parsing and tool-call-vs-text routing is FR-04's job |
| Tool conversion | `to_openai_tools()` adapter lives in `llm.py` | The tool adapter, the `OpenAI(...)` construction, the `chat.completions.create` call, and the `ChatCompletion` return type are all confined to `llm.py`, so `llm.py` is the single provider seam |
| Automated tests | Pure functions only (`from_env`, `to_openai_tools`); no network tests | User tests the client manually via `scripts/smoke_llm.py` |

## Files

```
pyproject.toml                 # + openai>=1.40 dependency
src/alokasi_agent/llm.py       # LLMConfig, LLMClient, to_openai_tools
scripts/smoke_llm.py           # manual verification harness (user-run)
tests/test_llm.py              # pure-function tests only, no network
```

## `llm.py` contents

1. **`LLMConfig`** — frozen dataclass:
   - `model: str = "gpt-4o-mini"`, `temperature: float = 0.0`, `timeout: float = 30.0`
   - `api_key: str`, `base_url: str | None = None`
   - `LLMConfig.from_env()` reads `OPENAI_API_KEY` (required — raises with a clear message if absent), `OPENAI_BASE_URL` (optional), and `ALOKASI_MODEL` / `ALOKASI_TEMPERATURE` / `ALOKASI_TIMEOUT` overrides

2. **`LLMClient`**
   - `__init__(config: LLMConfig | None = None)` — defaults to `LLMConfig.from_env()`; builds one `openai.OpenAI(api_key=..., base_url=..., timeout=...)`; SDK default retries (2) left untouched
   - `complete(messages: list[dict], tools: list[dict] | None = None) -> ChatCompletion` — injects `model` and `temperature` from config, passes `messages`/`tools` through, returns the raw response

3. **`to_openai_tools(tool: dict) -> list[dict]`** — converts `{name, description, input_schema}` to `[{"type": "function", "function": {"name", "description", "parameters"}}]`

## `scripts/smoke_llm.py`

Manual harness: sends the FRD §6 example message with `to_openai_tools(CREATE_ALOKASI_TOOL)` attached, prints whether a `create_alokasi` tool call arrived and its arguments — or the plain text reply if the model asked a clarification. Run with `.venv\Scripts\python.exe scripts\smoke_llm.py`. Supports `--dry-run` to check wiring (tool conversion + argument assembly) without spending a token.

## Out of scope (later work)

- System prompt: role, tool-use rules, "never guess missing fields" → Slice B
- Current date + WIB timezone injection → Slice B
- Live tool-call verification as an automated done-check → Slice B
- Response routing (tool call vs text), envelope building → FR-04
- Retry/backoff and error mapping → FR-11
- Non-OpenAI providers → only `to_openai_tools` would change
