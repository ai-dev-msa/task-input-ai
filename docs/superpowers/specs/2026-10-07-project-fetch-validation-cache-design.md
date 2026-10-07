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
