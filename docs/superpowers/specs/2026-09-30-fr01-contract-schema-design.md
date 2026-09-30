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
| `hasil_ci3` typing | Typed fields + `extra="allow"` | CI3 is built in a parallel track; unknown fields must not break the envelope |
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

3. **`HasilCI3(BaseModel)`** — §8.4 fields: `success: bool`, `type: str`, `message: str`, `database: str`, `data: dict[str, Any]`. `model_config = ConfigDict(extra="allow")`.

4. **`ResponseEnvelope(BaseModel)`** — `success: bool`, `type: str`, `function_name: str`, `arguments: str` (JSON **string**, per sample §8.5), `hasil_ci3: HasilCI3 | None`, `raw_message: str`, `user_id: str | None = None`. Also `extra="allow"`.

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
- `ResponseEnvelope` parses the §8.5 full sample envelope
- `hasil_ci3` accepts an unknown extra field without error
