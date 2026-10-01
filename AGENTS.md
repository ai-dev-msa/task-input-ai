# AGENTS.md

Standing instructions for any agent working in this repo. Follow them on every
task, in every session.

## What this repo is

The AI track of the `create_alokasi` natural-language allocation agent.
The requirements live in `PRD_FRD_create_alokasi_agent.md`. Work through the
FRD step by step, one FR at a time, in the suggested order (section 10).
The CI3 backend is a separate track: this repo never talks to CI3.

## How to write code here

- Simplest possible solution that works. Beginner-readable.
- Plain functions over classes. No classes, no abstractions, no layers.
- Do not add features, abstractions, or error handling that was not asked for.
- Keep changes minimal. Do not refactor unrelated code.
- Prefer the standard library. Keep a third-party library only while its code
  is still used; remove dependencies that become unused.
- Only make new files if needed. Prefer editing existing files.
- Explain anything non-obvious in a comment.
- Do not commit unless explicitly asked.

## Scope discipline

- Implement only the FR (or the explicit request) at hand. Do not pre-build
  future FRs.
- Leave items marked TBD in the PRD/FRD open on purpose.

## Verify before reporting done

- Tests: `.venv\Scripts\python.exe -m pytest`
- Live FR-04 check (needs `OPENAI_API_KEY`): `.venv\Scripts\python.exe scripts\smoke_agent.py`
