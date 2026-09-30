# FR-01 Design: Tool Schema and Contract (`create_alokasi`)

Date: 2026-09-30
Source: `PRD_FRD_create_alokasi_agent.md` §8, FR-01 (#1)
Status: approved

## Goal

One shared contract file that the prompt, the validator, and the tests all import. Nothing else in FR-01.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Stack | Python 3.11+ / Pydantic v2 | FR-05 names Pydantic; src layout grows into FR-02..FR-15 |
| Required arguments | All 6 | Strict schema; missing values are handled by FR-07's clarification loop, not by optional fields |
| Layout | `src/alokasi_agent/schema.py` + `tests/` (pytest) | Single file for the contract |
| Boundary | **AI-only**: extract → validate locally → return; no CI3 contact (decision 2026-09-30) | This repo must not define or call the backend; FR-03/FR-10/FR-11 moved to the backend track |
| `hasil_ci3` | **Removed from this repo** — not modeled here at all | CI3's response shape is owned by the backend codebase; a copy here would drift (was: typed + `extra="allow"`) |
| Tool shape | Provider-neutral `{"name", "description", "input_schema"}` | LLM provider is TBD (FR-02 adapts it) |
| Empty values | `min_length=1` on free-text fields | Approved at final review 2026-09-30; empty must mean "ask the user", not "write blank data" |

## Files

```
pyproject.toml                          # pydantic + pytest deps, src layout
src/alokasi_agent/__init__.py
src/alokasi_agent/schema.py             # the single shared contract
scripts/update_golden.py                # regenerates the golden schema snapshot
tests/test_schema.py
tests/golden/create_alokasi_input_schema.json
```

## `schema.py` contents

1. **`CreateAlokasiArgs(BaseModel)`** — six non-Optional `str` fields: `nama_karyawan`, `nama_proyek`, `tanggal`, `jenis_pekerjaan`, `jam_mulai`, `jam_selesai`.
   - `tanggal`: `pattern=r"^\d{4}-\d{2}-\d{2}$"` (§8.2 `YYYY-MM-DD`)
   - `jam_mulai`, `jam_selesai`: `pattern=r"^\d{2}:\d{2}$"` (§8.2 `HH:MM`)
   - Every field carries a description drawn from §8.2 so it surfaces in the tool definition the LLM sees.
   - `extra="forbid"`: a hallucinated 7th argument is a validation error, not silently dropped.
   - Non-Optional ⇒ all six land in the generated JSON Schema `required` list automatically.
   - `min_length=1` on the three free-text fields, so an empty value reads as missing and reaches FR-07's clarification loop rather than CI3.

2. **`CREATE_ALOKASI_TOOL: dict`** — `{"name": "create_alokasi", "description": ..., "input_schema": CreateAlokasiArgs.model_json_schema()}`. Derived from the model, so prompt and validator cannot disagree.

3. **`ResponseEnvelope(BaseModel)`** — `success: bool`, `type: str`, `function_name: str`, `arguments: str` (JSON **string**, per sample §8.5), `raw_message: str`, `user_id: str | None = None`. `extra="allow"`.

   This is the AI track's output only. The `hasil_ci3` field and the `HasilCI3` model were removed on 2026-09-30 (boundary decision): the backend adds `hasil_ci3` to the full §8.5 envelope itself, and its shape (§8.4) is defined solely by the CI3 codebase. This repo passes nothing of CI3's through, because it never talks to CI3.

## Boundary (decided 2026-09-30)

This repo is AI-only: `raw_message` → LLM extraction → local validation of the 6 arguments → return (result or clarification question). It makes no HTTP call to CI3, models no CI3 response, and performs no backend write. FR-03 (CI3 API client), the write-gating half of FR-10, and FR-11 (backend error handling) are owned by the backend track — see the annotated PRD.

## Out of scope (assigned to later FRs)

- Calendar/time validity (reject `2026-13-45`, `99:99`) and `jam_selesai > jam_mulai` → FR-05
- Retry/fallback on validation failure → FR-05
- Building the envelope from an LLM result → FR-04
- Provider-specific tool format (OpenAI `function` / Anthropic `input_schema`) → FR-02
- Date/time normalization → FR-06

## Tests

- All six args appear in `input_schema.required`
- The §6 sample arguments validate and round-trip through the model
- `tanggal` outside `YYYY-MM-DD` and `jam` outside `HH:MM` are rejected by pattern
- Golden snapshot: `CREATE_ALOKASI_TOOL["input_schema"]` matches `tests/golden/create_alokasi_input_schema.json`; drift fails the suite
- `ResponseEnvelope` parses the §8.5 sample (extra fields such as `hasil_ci3` pass through untouched — `extra="allow"`)
- Unknown extra envelope fields are tolerated
