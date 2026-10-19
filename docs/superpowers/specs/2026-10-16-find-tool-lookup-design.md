# find_employee / find_project lookup tools (2026-10-16)

Replace the full employee/project lists injected into the system prompt with
two lookup tools. The lists stay in code (matching only); the canonical name
reaches the LLM through a `role:"tool"` result after the model asks for it.

## Decisions (user-approved)

- Trigger: the LLM calls the lookup tools (Approach A — extend the existing
  tool flow in `agent.py`, not a pre-pass or two-phase design).
- Match source: caller-supplied `employees`/`projects` lists passed to `run()`
  (contract unchanged; this repo still performs no DB/ERP lookups, PRD §6).
- Tool shape: two tools — `find_employee(name)` and `find_project(name)`.
- Skip-lookup: fail closed. A non-canonical name in `create_alokasi` gets a
  tool error telling the model to call `find_*` first (no straight-to-user
  question from code); clarification still reaches the user via the model
  after a tool result shows candidates (FR-09 kept).
- Matcher: `difflib` (stdlib), same `get_close_matches(n=3, cutoff=0.5)` as
  today. No rapidfuzz dependency.
- Hard requirement: the full list fetched by the endpoint is NEVER injected
  into the system prompt.

## Data flow

```
POST /chat (main.py unchanged: fetch + TTL cache + pass lists to run())
  -> run()
       system prompt: static rules -> now_wib -> user   (lists gone)
       round 1: model calls find_employee/find_project with typed names
                code matches vs lists -> role:"tool" result:
                  exact      -> "Matched: <canonical spelling>"
                  ambiguous  -> "No exact match ... Closest: a, b, c. Ask user."
                  none       -> "Not found ... Ask user to check the name."
                  empty list -> "Employee/Project list unavailable..."
       round 2: model calls create_alokasi with canonical names
       validate (FR-05) -> membership (redirect) -> FR-08 row guard -> accept
       _canonicalize_row -> function_call envelope (unchanged)
```

## Tool contracts (`schema.py`)

- `FIND_EMPLOYEE_TOOL`: name `find_employee`, `input_schema` `{name: string}`
  required. Description: resolve a person name against the employee list;
  call for every assignee and tim_pekerjaan member before `create_alokasi`.
- `FIND_PROJECT_TOOL`: name `find_project`, same shape, for project names.
- Provider-neutral shape (`name`/`description`/`input_schema`) like
  `CREATE_ALOKASI_TOOL`. Tool results are free text (no output schema), the
  same as FR-05 validation replies.
- `llm.to_openai_tools(*tools)` becomes variadic (still accepts one).

## Prompt (`prompt.py`, working-tree version)

- Delete the `{{employee_list}}` / `{{project_list}}` slots; `build_system_prompt`
  signature drops `employees`/`projects` (now `(now, user_name)`).
- Field rules: "Must match the list exactly" -> resolve via `find_*` first;
  use the spelling the tool returned; candidates -> ask user; not found -> ask
  user. tim_pekerjaan: resolve every member via `find_employee`; if not found,
  ask whether to fix or drop the name (keeps the old `offer_delete` intent).
- `# Before calling`: "names match the lists character for character" ->
  "every name came from a find_employee/find_project result".
- `# Scope`: "questions answerable from the data in this prompt" -> also
  covers `find_*` results in this conversation.
- `# Flow`: add a step before the confirmation summary: resolve all names
  with `find_*` first; do not ask for confirmation until every name resolved.
- `# Examples`: replace "always use the lists below" with "names in examples
  are illustrative; always resolve real names through find_* first". Example
  summaries themselves stay (they pin the parseable summary format).
- Context keeps only `now_wib` + `current_user_name`, both after the static
  block (prefix-cache ordering preserved, `test_prompt.py:140` reworded).

## Loop (`agent.py`)

One bounded round loop replaces the linear flow (up to `MAX_ROUNDS = 6`
`complete()` calls, refusing when exhausted):

1. `complete(messages, tools)` — tools = create_alokasi + both find_*.
2. Message has `find_*` calls -> reply `role:"tool"` for EVERY call id
   (find_* gets the match result; any create_alokasi in the same turn gets
   "OK" and is not acted on) -> next round.
3. `create_alokasi` calls: FR-05 format validation first; errors ->
   existing one-retry reply -> next round (unchanged semantics).
4. Membership: `_employee_problem` / `_project_problem` / `_tim_problem`
   still run, but their text is now a **redirect error** per bad value:
   `<value> is not resolved. Call find_employee (or find_project) with the
   intended name, then resend create_alokasi.` -> `role:"tool"` reply ->
   next round (max 2 redirects). The user-facing "Maksud kamu X?" now comes
   from the model after it sees a tool result with candidates.
5. Empty lists: `_missing_lists_message` refusal kept for create_alokasi;
   `find_*` on an empty list returns the "list unavailable" tool result.
6. FR-08 row guard nudge: unchanged, once.
7. Accept: `_canonicalize_row` + envelope build unchanged; plain-text
   envelope path (greetings, model's clarification question) unchanged.

Budget accounting: 1 initial + 1 redirect + 1 find + 1 resubmit + 1 FR-05
retry + 1 row guard = 6 rounds fits the common worst case exactly.
Counters: FR-05 format retry once, redirects max 2, row-guard nudge once —
find_* rounds do not count against any counter (a find_* reply always ends
that round). Rarer chains (second redirect stacked on FR-05 retry + row
guard) run past 6 and land on the refusal — safe by construction: at worst
the user gets an error instead of a wrong write.

## Error handling

| Case | Behavior |
|---|---|
| Caller sends empty lists | create_alokasi refused before ERP (unchanged); find_* returns "list unavailable" |
| find_* fuzzy match | candidates in tool result -> model asks user |
| find_* zero match | "not found" in tool result -> model asks user to recheck |
| Unresolved name in create_alokasi | redirect tool error (max 2), then refuse |
| Bad JSON in find_* arguments | tool result "could not read the name, retry" |
| Unknown tool name | ignored (existing `_alokasi_calls` filter) |
| Budget exhausted | `type:"error"` refusal envelope (existing shape) |

## Tests

- `test_prompt.py`: built prompt contains no list content (assert markers
  `Valid employees`/`Valid projects` gone + no injected names possible via
  new signature); reword the 6 pre-existing failing markers (they pin the
  pre-rewrite wording) plus the changed rules above.
- `test_agent.py`: find_* result texts (exact / ambiguous / none / empty
  list); redirect -> find_* -> resubmit accept sequence via a scripted
  `complete` stub; tim member resolution; redirect budget exhaustion ->
  refusal; canonical-name calls still accepted without any find_* round
  (keeps most existing tests green).
- `test_schema.py`: shape checks for the two new tools; golden
  `create_alokasi` snapshot untouched.
- `test_llm.py`: `to_openai_tools` with multiple tools.

## Verification

1. `.venv\Scripts\python.exe -m pytest`
2. Live: `.venv\Scripts\python.exe scripts\smoke_agent.py` (OPENAI_API_KEY)
3. `.venv\Scripts\python.exe scripts\run_eval.py` — token counts shift
   (prompt down, extra rounds up) -> refresh `eval/baseline.json`.

## Docs / FRD

- `docs/integration-guide.md` lines ~146-148 and ~202-205: lists are still
  required on every request but are the matching source for find_* tools,
  not prompt content; names are resolved by the tools + model, checked by
  code.
- `PRD_FRD_create_alokasi_agent.md`: FR-02 delivered note (injected-context
  contract amended: lists no longer injected) and FR-09 (resolution moved
  into find_* tools).

## Out of scope

DB/ERP access in this repo, rapidfuzz, `main.py` fetch logic, FR-15, the
`test_main_chat.py` server-only import error, callers' contract changes.
