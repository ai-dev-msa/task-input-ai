# Integration Guide: putting `main.py` in front of the AI repo

This guide explains how to turn the old all-in-one Flask file (`main.py ai.txt`
in the repo root, kept as a reference) into a **wrapper**: all the AI logic
moves into this repo's `alokasi_agent` package, while `main.py` keeps the HTTP
glue **and the backend step** that writes the allocation to the ERP.

Written for a complete beginner. Read Part A first (the ideas), then Part B
(the hands-on steps).

---

# Part A — The big picture

## 1. Two pieces, one job

Think of it as a restaurant:

| Piece | Role | Speaks |
|---|---|---|
| `main.py` (new, ~190 lines) | The **receptionist and the courier**. Accepts HTTP requests, asks the brain, and — once the user confirms — delivers the row to the ERP and reports back. | HTTP / JSON |
| `alokasi_agent` package (`src/alokasi_agent/`) | The **brain**. It takes a user message and decides: ask a question, or produce a `create_alokasi` tool call. | Python |

The receptionist never thinks. The brain only talks to the OpenAI API — it
knows nothing about ERP URLs or tokens, and it never imports `requests`. That
split is the whole point:

- The brain is tested by `tests/` and `scripts/`. Editing `main.py` can never
  break the AI logic, because `main.py` does not contain any.
- The same brain can later be reused somewhere else (a CLI, a queue consumer,
  another endpoint) without copy-pasting the prompt or schema.

### Why the backend code stays in `main.py`

The old file logs into the ERP (`get_erp_token`), validates its token, and
POSTs the allocation to `appweb.co.id`. **All of that stays.** After `run()`
returns `type: "function_call"`, `main.py` performs the write itself and adds
`hasil_ci3` to the response — it plays the backend's role inside this service.

What moves out is only the code the AI repo already has: the tool schema, the
system prompt, and the OpenAI call (see section 2).

> **Deliberate deviation from the PRD.** PRD §8.3 and FR-03 describe a world
> where the AI returns `arguments` and the *caller* performs the write, and the
> AI package stays CI3-free — it still is: `src/alokasi_agent/` never imports
> `requests` and knows no ERP URL. Here the choice is to keep the write in
> `main.py`, so the response the caller sees gains `hasil_ci3` again. This note
> exists so nobody later "fixes" the guide back.

The old file had a real bug in this area: its CI3 debug prints (old lines
307–310) ran **before** `response_ci3` was assigned, so every tool call died
with `NameError`. The new listing keeps only the working prints (old lines
324–327), which sit right after the POST — the broken duplicate is simply gone.

## 2. Who owns what

### Stays in `main.py`

| Piece | Why |
|---|---|
| `Flask(__name__)` app | It is the HTTP server. |
| `GET /` health check | Unchanged: `{"success": true, "message": "AI Service running"}`. |
| `POST /chat` route | The only real endpoint. It parses the request, calls `run(...)`, performs the ERP write when the model produced a tool call, returns the envelope. |
| CORS limited to `/chat`, origin `https://appweb.co.id` | The browser (MIS web app) calls only this route. |
| `load_dotenv("./.env", override=True)` | Puts `OPENAI_API_KEY`, `ALOKASI_*` and `ERP_API_*` into the environment before they are read. |
| `get_erp_token()` + `ERP_API_USERNAME` / `ERP_API_PASSWORD` | The write half: logs into the ERP for a bearer token. Kept as-is. |
| `requests.get(".../auth/validate")` + its prints | Kept as-is: proves the token works before writing. |
| `requests.post(".../aialokasiharian/createAlokasi")` + `hasil_ci3` | `main.py` performs the write after the confirmation, then returns `hasil_ci3` to the caller. |
| The CI3 status/response prints | Kept: the working pair after the POST (old lines 324–327) stays; the broken duplicate (old 307–310) is dropped. |
| `import requests`, `import json`, `import os` | ERP calls, parsing `envelope["arguments"]` before the POST, reading the ERP credentials. |
| The generic error reply (section 6) | HTTP glue: never leak exceptions or ERP response text to the caller. |
| `if __name__ == "__main__": app.run(host="0.0.0.0", port=5001, debug=False)` | How the service is started. |

### Already in the AI repo — do NOT paste it back

| Old code in `main.py ai.txt` | Where it lives now |
|---|---|
| The inline `tools` list (old lines 55–100) | `src/alokasi_agent/schema.py` → `CREATE_ALOKASI_TOOL` (+ golden test in `tests/golden/`) |
| The inline `system_prompt` string (old lines 103–267) | `src/alokasi_agent/prompt.py` → `PROMPT_TEMPLATE` / `build_system_prompt(...)` |
| `client.responses.create(...)` (old lines 270–280) | `src/alokasi_agent/llm.py` → `complete()`. Model/timeout/temperature come from `.env` (`ALOKASI_MODEL`, `ALOKASI_TIMEOUT`, `ALOKASI_TEMPERATURE`). |
| Loop over `response.output` + `json.loads(item.arguments)` (old lines 284–301) | `src/alokasi_agent/agent.py` → `run()` returns the envelope; the ERP block in section 6 runs after it |
| (nothing — the old file never validated) | `src/alokasi_agent/schema.py` → `validate_arguments()`; `run()` retries the model once with the errors (FR-05) |
| Conversation handling | `run()` threads `history` in and out; the envelope carries `history` (FR-16) |
| Confirmation flow ("Benar?"), multi-row records, edit/cancel rules | Prompt rules in `prompt.py` (FR-07/FR-08/FR-10) |

> **Important:** the prompt in this repo is **newer** than the one inside
> `main.py ai.txt`. It uses the MSA identity, project `OPRS Divisi WIN 2026`,
> and adds inline-edit and cancel rules. Never copy the old prompt over it.

### Deleted from `main.py` — only what the package duplicates or replaces

| Piece | Why it is gone |
|---|---|
| `from openai import OpenAI` + `client = OpenAI(...)` (old lines 4, 29) | `llm.complete()` builds its own client from `OPENAI_API_KEY`; nothing in `main.py` touches the SDK anymore. |
| The inline `tools` list, the inline `system_prompt`, `client.responses.create(...)`, the `response.output` loop | Already covered by the table above (`schema.py` / `prompt.py` / `llm.py` / `agent.py`). The old file even sent the `{{now_wib}}` placeholders to the model unsubstituted — `build_system_prompt()` fills them now. |
| The response field name `answer` | Renamed to `reply` by `run()` (PRD §8.3) — callers must read `reply`. |

Note the *place* of the backend block also changes: the old file did the ERP
POST inside the model-output loop; the new one does it right after `run()`
returns `type: "function_call"`. Same job, one clear spot.

## 3. Target folder structure

```
project-root/                  <- this repo
  main.py                      <- Flask wrapper + ERP write (~190 lines, section 6)
  main.py ai.txt               <- OLD reference file; delete it once main.py exists
  .env                         <- OPENAI_API_KEY, ALOKASI_* + ERP_API_USERNAME/ERP_API_PASSWORD
  .env.example
  requirements.txt             <- NEW: flask, flask-cors, requests
  pyproject.toml               <- unchanged (the package definition)
  src/alokasi_agent/
    __init__.py                <- exports run
    agent.py                   <- run(...)
    schema.py                  <- tool schema + validate_arguments()
    prompt.py                  <- build_system_prompt(...)
    llm.py                     <- complete() (the only OpenAI call)
  tests/                       <- pytest suite
  scripts/                     <- smoke_llm.py, smoke_agent.py, update_golden.py
  docs/                        <- this guide
```

`pip install -e .` installs the package from `pyproject.toml` into your virtual
environment in "editable" mode: Python can `import alokasi_agent` from anywhere,
and edits to `src/` take effect immediately without reinstalling. You run it
once per machine/venv.

## 4. The contract with the caller (MIS web / CI3 front-end)

### Request — `POST /chat`, JSON body

| Field | Required | Type | Meaning |
|---|---|---|---|
| `message` | **yes** | string | What the employee typed. Missing → HTTP 400. |
| `user_id` | no | string / null | Passed through into the envelope unchanged. |
| `user_name` | no | string | The logged-in employee's name. Used when the message says "aku/saya". |
| `employees` | no | array of strings | The valid employee names **for this request**. |
| `projects` | no | array of strings | The valid project names **for this request**. |
| `history` | no | array of `{role, content}` | What the previous response returned. Empty/absent on the first turn. |

**The service is stateless.** It stores nothing between requests. So the caller must:

1. Send `history` back **unchanged** from the last response. If it drops it,
   turn 2 ("ya") arrives with no memory of the summary it is confirming, and
   the conversation falls apart.
2. Send `employees` and `projects` on **every** request. The AI side performs
   no database lookups (PRD boundary §6) — it can only check names against the
   lists you send.

### Response — JSON body (the envelope)

| Field | Meaning |
|---|---|
| `success` | `true` normally; `false` on an error turn. |
| `type` | `text` \| `function_call` \| `error`. |
| `function_name` | `"create_alokasi"` on a tool call, otherwise `""`. |
| `arguments` | JSON **string** of the arguments on a tool call, otherwise `""`. |
| `raw_message` | The user message you sent, echoed back. |
| `user_id` | Whatever you sent, echoed back (`null` if you sent none). |
| `reply` | The model's text: a confirmation summary or a clarifying question. May be `null` on a tool call. |
| `history` | The conversation **after** this reply. Store it; send it back next turn. |
| `hasil_ci3` | **Only on `type: "function_call"`:** the ERP write result. One object for a single row (the shape documented in PRD §8.4), an array of objects when several rows were written. Added by `main.py`, not by `run()`. |

> The old file used the field name `answer`; it is `reply` now (PRD §8.3).

Example (`type: "text"`, turn 1 of a confirmation):

```json
{
  "success": true,
  "type": "text",
  "function_name": "",
  "arguments": "",
  "raw_message": "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 ...",
  "user_id": "U-01",
  "reply": "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN | 09:00-12:00. Benar?",
  "history": [
    {"role": "user", "content": "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 ..."},
    {"role": "assistant", "content": "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN | 09:00-12:00. Benar?"}
  ]
}
```

### What the caller does with each `type`

| `type` | Caller action |
|---|---|
| `text` | Show `reply` to the user. Send the next message back with the same `history`. |
| `function_call` | **Nothing left to write** — `main.py` already POSTed the row(s) to the ERP. Display `hasil_ci3` (the ERP's own success message) and store `history`. |
| `error` (with `success: false`) | Show `reply` to the user. |

### Two details worth knowing

- **Multi-row:** if the employee confirms several allocations at once,
  `arguments` is a JSON **array** string (`[{...}, {...}]`); a single row is an
  object string. `main.py` handles both: it parses `arguments`, makes one POST
  per row, and returns `hasil_ci3` as an object (one row) or an array
  (several). (PRD FR-08.)
- **Names are checked by the model, not by code.** `validate_arguments()`
  checks *formats* (dates, times, non-empty). Whether `"Imam Ihsani"` really
  exists depends on the `employees` list you sent — which is why you must send
  it every turn.

---

# Part B — Hands-on

## 5. Setup (once)

```powershell
# 1. activate your virtual environment, then:
.venv\Scripts\python.exe -m pip install -e .        # installs the alokasi_agent package
.venv\Scripts\python.exe -m pip install -r requirements.txt   # flask, flask-cors, requests
```

`requirements.txt` (create it, three lines):

```
flask
flask-cors
requests
```

`.env` keys:

| Key | Required | Notes |
|---|---|---|
| `OPENAI_API_KEY` | **yes** | Without it, `run()` raises `OPENAI_API_KEY is not set...`. |
| `ERP_API_USERNAME` | **yes, for writing** | ERP login used by `get_erp_token()`. Without it, every confirmed turn ends in the generic error envelope. |
| `ERP_API_PASSWORD` | **yes, for writing** | Same. |
| `ALOKASI_MODEL` | no | Defaults to `gpt-4o-mini`. The old file used `gpt-5.6-luna` — set this if you want it back. |
| `ALOKASI_REASONING_EFFORT` | for reasoning models | `gpt-5.6-luna` needs `ALOKASI_REASONING_EFFORT=none` when used with function tools. |
| `ALOKASI_TEMPERATURE` | no | Default `0.0`. |
| `ALOKASI_TIMEOUT` | no | Seconds, default `30`. |
| `OPENAI_BASE_URL` | no | Only if you use a proxy/gateway. |

## 6. The complete `main.py`

Create `main.py` in the repo root:

```python
import json
import os

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from alokasi_agent import run

load_dotenv("./.env", override=True)

app = Flask(__name__)

# CORS: only the MIS web app may call /chat from a browser.
CORS(
    app,
    resources={
        r"/chat": {
            "origins": [
                "https://appweb.co.id"
            ]
        }
    },
    methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "AI Service running"
    })


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}

    # message is the only required field.
    message = data.get("message")
    if not message:
        return jsonify({
            "success": False,
            "type": "error",
            "reply": "message wajib diisi",
            "history": []
        }), 400

    try:
        # 1) All AI logic lives in run(). It returns (envelope, history);
        #    the envelope already contains reply + history.
        envelope, _history = run(
            message,
            user_name=data.get("user_name") or "",
            employees=data.get("employees") or [],
            projects=data.get("projects") or [],
            history=data.get("history") or [],
            user_id=data.get("user_id"),
        )
        body = dict(envelope)

        # 2) The backend half (kept from the old file): only a confirmed
        #    tool call is written to the ERP.
        if body["type"] == "function_call":
            # arguments is a JSON string: one object (single row) or an
            # array of objects (several rows, FR-08).
            parsed = json.loads(body["arguments"])
            single_row = isinstance(parsed, dict)
            rows = [parsed] if single_row else parsed

            token = get_erp_token()

            # Probe: confirm the token works before writing.
            response_validate = requests.get(
                "https://appweb.co.id/apiv1/auth/validate",
                headers={
                    "Authorization": f"Bearer {token}"
                },
                timeout=30
            )
            print("VALIDATE HTTP:", response_validate.status_code)
            print("VALIDATE RESPONSE:", response_validate.text)

            # One POST per row.
            results = []
            for row in rows:
                response_ci3 = requests.post(
                    "https://appweb.co.id/apiv1/aialokasiharian/createAlokasi",
                    json=row,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )
                print("CI3 HTTP STATUS:", response_ci3.status_code)
                print("CI3 RESPONSE:", response_ci3.text)
                results.append(response_ci3.json())

            # One row keeps hasil_ci3 an object (the shape callers know);
            # several rows return an array of results.
            body["hasil_ci3"] = results[0] if single_row else results

        return jsonify(body)

    except Exception as e:
        # Log the real error here (server-side only); the caller gets a
        # generic message, never the exception text.
        print("ERROR /chat:", repr(e))
        return jsonify({
            "success": False,
            "type": "error",
            "function_name": "",
            "arguments": "",
            "raw_message": message,
            "user_id": data.get("user_id"),
            "reply": "Terjadi kesalahan, coba lagi.",
            "history": data.get("history") or []
        })


# buat login otomatis ke MIS biar langsung dapetin tokennya
# (kept from the old file, unchanged)
def get_erp_token():

    username = os.getenv("ERP_API_USERNAME")
    password = os.getenv("ERP_API_PASSWORD")

    if not username or not password:
        raise Exception("ERP_API_USERNAME / ERP_API_PASSWORD belum tersedia")

    response_login = requests.post(
        "https://appweb.co.id/apiv1/auth/login",
        data={
            "username": username,
            "password": password
        },
        timeout=30
    )

    #++VVVVVV Cek response HTTP
    if response_login.status_code != 200:
        raise Exception(
            "Login ERP gagal. HTTP " +
            str(response_login.status_code) +
            " | Response: " +
            response_login.text
        )
    #//++VVVVVV

    #++VVVVVV Parse JSON response
    hasil_login = response_login.json()
    #//++VVVVVV

    #++VVVVVV Response login berbentuk list
    if not isinstance(hasil_login, list) or not hasil_login:
        raise Exception(
            "Format response login ERP tidak sesuai. Response: " +
            str(hasil_login)
        )
    #//++VVVVVV

    #++VVVVVV Ambil object login pertama
    data_login = hasil_login[0]
    #//++VVVVVV

    #++VVVVVV Ambil access token
    token = data_login.get("access_token")

    if not token:
        raise Exception(
            "Access token tidak ditemukan dari response login ERP"
        )
    #//++VVVVVV

    return token


# Start the service: python main.py  (http://0.0.0.0:5001)
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False
    )
```

### Things that are deliberately NOT in this file

| You might expect | Why it is absent |
|---|---|
| `client = OpenAI(...)` | `llm.complete()` creates its own client from `OPENAI_API_KEY`. There is no `client=` parameter on `run()` — that only ever appeared in stale FRD text; the real signature is `run(raw_message, *, user_name, employees, projects, history, user_id, now, complete)`. |
| `now=...` | Optional. The prompt converts whatever time it gets to WIB (Asia/Jakarta) itself, so `datetime.now(UTC)` — the default — already renders the correct WIB clock. |
| The `tools` list / system prompt / `responses.create` | Duplicated in the old file, owned by `schema.py`, `prompt.py`, `llm.py`. That is exactly the code this integration deletes. |
| The `response.output` parsing loop | `run()` hands you a ready-made envelope; the backend block only runs when `type == "function_call"`. |
| `json.loads` of raw model output | You only parse `envelope["arguments"]` (before the ERP POST) — `run()` did all the model-output parsing. |

### What IS in this file that the old AI-only design didn't need

Everything backend: `get_erp_token()`, the `auth/validate` probe, the
`createAlokasi` POST, `hasil_ci3`, the prints, `import requests/json/os`, and
the two ERP credentials in `.env`. All of it kept from `main.py ai.txt`; only
its position changed (it now runs after `run()` instead of inside the
model-output loop), and the one broken print pair (old lines 307–310, the
`NameError`) is dropped because the working prints after the POST already
print the same thing.

## 7. Verify it works

### Automated checks (no server needed)

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe scripts\smoke_agent.py      # live; needs OPENAI_API_KEY
```

`pytest` must pass; `smoke_agent.py` exits 0 when a live conversation ends with
the PRD sample arguments.

### Live checks with curl

Start the service in one terminal:

```powershell
.venv\Scripts\python.exe main.py
```

Tip: save each request body below as `chat1.json`, `chat2.json`, ... next to
where you run curl, and use `-d "@chat1.json"` (avoids quoting pain in
PowerShell).

**Curl 1 — missing `message` → HTTP 400**

```
curl -X POST http://localhost:5001/chat -H "Content-Type: application/json" -d "{}"
```

Expect: `400` with `{"success": false, "type": "error", "reply": "message wajib diisi", ...}`.

**Curl 2 — the PRD sample message → `type: "text"` (the confirmation)**

`chat1.json`:

```json
{
  "message": "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026",
  "user_id": "U-01",
  "user_name": "Andi Wijaya",
  "employees": ["Imam Ihsani", "Budi Santoso"],
  "projects": ["OPRS Divisi WIN 2026"],
  "history": []
}
```

```
curl -X POST http://localhost:5001/chat -H "Content-Type: application/json" -d "@chat1.json"
```

Expect: `200`, `"type": "text"`, and a `reply` like
`Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN | 09:00-12:00. Benar?`
plus a `history` array with two turns.

> The model does **not** call the tool on turn 1 — the prompt requires a
> "Benar?" confirmation first (FR-10). That is correct behavior.

**Curl 3 — confirm with `"ya"` + the returned history → `function_call` + write**

> **Side effect:** this turn **writes a real row** to the ERP (TESTING) database.
> It also needs `ERP_API_USERNAME` / `ERP_API_PASSWORD` in `.env` and a
> reachable `appweb.co.id`. Without them you get the generic error envelope
> instead — check the `ERROR /chat:` line in the server log.

`chat2.json`: same fields as `chat1.json`, but

```json
{
  "message": "ya",
  "history": [
    {"role": "user", "content": "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026"},
    {"role": "assistant", "content": "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN | 09:00-12:00. Benar?"}
  ]
}
```

(Paste the exact `history` curl 2 returned — don't retype it.)

```
curl -X POST http://localhost:5001/chat -H "Content-Type: application/json" -d "@chat2.json"
```

Expect: `"type": "function_call"`, `"function_name": "create_alokasi"`,
`arguments` equal to:

```json
{"nama_karyawan": "Imam Ihsani", "nama_proyek": "OPRS Divisi WIN 2026", "tanggal": "2026-09-29", "jenis_pekerjaan": "Development Modul PPN", "jam_mulai": "09:00", "jam_selesai": "12:00"}
```

and — because `main.py` performs the write — a `hasil_ci3` object from the
ERP (with `success`, `type: "created"`, `message: "Alokasi berhasil dibuat"`,
`data`, ... see PRD §8.4). The prints `VALIDATE HTTP:` / `CI3 HTTP STATUS:`
appear in the server terminal.

This is the FR-04 done-condition: the sample message produces exactly the PRD
sample arguments.

> If instead you get `success: false` with `reply: "Terjadi kesalahan, coba
> lagi."`, the AI part worked but the ERP write failed — go to section 8.

**Curl 4 — partial message, then the answer (the clarification loop)**

`chat3.json`: fresh turn (`history: []`), message:

```json
{"message": "besok aku ngerjain modul PPN jam 1 sampai jam 4", "user_id": "U-01", "user_name": "Andi Wijaya", "employees": ["Imam Ihsani", "Budi Santoso"], "projects": ["OPRS Divisi WIN 2026"], "history": []}
```

Expect `type: "text"` and a short question (which project / whose name / date).

Then `chat4.json`: your answer, with **that response's `history` pasted in**:

```json
{"message": "proyek OPRS Divisi WIN 2026", "user_id": "U-01", "user_name": "Andi Wijaya", "employees": ["Imam Ihsani", "Budi Santoso"], "projects": ["OPRS Divisi WIN 2026"], "history": [ ...paste history from chat3... ]}
```

Keep answering until you get `"type": "function_call"` (usually 2–3 turns: the
clarification, then `Benar?`, then `ya`) — that final turn also writes a row
to the ERP, same side effect as curl 3.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'alokasi_agent'` | You skipped `pip install -e .` (or ran a different Python than the venv). |
| `OPENAI_API_KEY is not set. Export it before calling complete().` | `.env` is missing the key, or you started `main.py` from a folder where `./.env` isn't found (run it from the repo root). |
| Confirmed turn comes back as `reply: "Terjadi kesalahan, coba lagi."` | The ERP write failed (the AI part had already succeeded). Check `ERP_API_USERNAME` / `ERP_API_PASSWORD` in `.env`, that `appweb.co.id` is reachable, then read the `ERROR /chat:` line in the server log — the real reason only exists there. |
| Server log shows `Login ERP gagal. HTTP ...` or `ERP_API_USERNAME / ERP_API_PASSWORD belum tersedia` | `get_erp_token()` could not log in: missing/wrong credentials or the ERP is down. Fix `.env` or the ERP; nothing is written while this fails. |
| You expected a write but none happened | Only `type: "function_call"` triggers the ERP POST. A `text` turn is just the confirmation question — answer it (`ya`) first. |
| Browser says CORS blocked | The calling page's origin must be exactly `https://appweb.co.id`. Server-to-server calls (curl, CI3) are unaffected by CORS. |
| Turn 2 replies as if it forgot everything | The caller did not send back the `history` from the previous response. |
| The model asks "siapa namanya?" / invents a project | The caller did not send `employees` / `projects`. Format validation can't catch a name that doesn't exist — only the list you send can. |
| Model surprises you with wrong tool behavior | Check `ALOKASI_MODEL` in `.env`; the default is `gpt-4o-mini`. For `gpt-5.6-luna` set `ALOKASI_REASONING_EFFORT=none`. |
| `OSError: [WinError 10048] ... port 5001` | An old `main.py` is still running — close it or change the port. |
| Want to compare with the pre-split service | Open `main.py ai.txt` (the old file, kept for reference). Delete it once your real `main.py` is in place. |
