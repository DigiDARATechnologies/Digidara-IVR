# DigiDARA — Engineering Guidelines

## Coding Principles

1. **Fix root causes, not symptoms.** Before writing a fix, trace the actual code path to the exact line that misbehaves. In this codebase, "the AI says goodbye but never hangs up" was not a vague flakiness issue — it was one `if language == "tamil":` guard around the hangup call, confirmed by reading `app/api/openai_realtime.py`'s `response.done` handler directly. Patch that line, not the symptom around it.
2. **No speculative abstraction.** Do not introduce a provider interface, config flag, or generic helper for a case that does not exist yet. The telephony provider abstraction (`app/services/telephony/`) exists because a second provider is a real, near-term possibility; a similar abstraction is *not* yet built for Google Sheets or CDR billing reconciliation, because there is exactly one concrete need there today. Add the abstraction when the second real case appears, not before.
3. **Model judgment over brittle pattern matching, for user intent specifically.** When a decision depends on interpreting open-ended natural language (e.g., "does this customer want the call to end"), prefer giving the LLM a tool to signal its judgment over maintaining an ever-growing regex list. Reserve regex/keyword matching for cases needing determinism and auditability — billing math, suppression-list matching, structured CRM disposition tagging.
4. **Every prompt is production code.** System-prompt and instruction-string changes (`conversation_policy_service.py`) go through the same scrutiny as application code: they are versioned, reviewed, and — where feasible — covered by a token-budget or content test (see `tests/test_conversation_policy_service.py`'s `estimate_prompt_tokens` assertions). Two live conversational bugs during this engineering pass were traced directly to prompt wording, not application code, which is the reason this rule exists explicitly rather than being assumed.
5. **Parameterize every SQL statement.** No f-string or `%`-formatted SQL values, ever. All queries use PyMySQL's parameter substitution (`%s` placeholders with a tuple/list of values passed separately).
6. **Keep API routers thin.** `app/api/*.py` files parse requests, call a service function, and shape the response. Business logic — including anything that decides *whether* an action is allowed (suppression checks, active-call de-duplication) — lives in `app/services/*.py`, not inline in a route handler.
7. **Don't build for hypothetical scale you don't have evidence for.** The lack of a Google Sheets provider abstraction, or of a queueing system for bulk calls, is a deliberate reflection of current single-provider, moderate-volume operation — not an oversight. Revisit when there is a second real need, per [ARCHITECTURE_DECISION_RECORD.md](#).

## Security Principles

- Never trust a Plivo webhook without validating its V3 HMAC signature first (`_signed_form` in `app/api/plivo.py`); this applies to every new webhook route added, with no exceptions for "internal-only" or "just for testing" endpoints.
- Never log or persist a raw credential. `api_credentials.credential_ciphertext` exists specifically so that provider credentials are stored encrypted, not in plaintext columns or `.env`-style flat files, once that table is actually wired into use.
- Treat every value pulled from a Google Sheet, campaign `ai_prompt`, or customer-supplied field as untrusted content when it flows into a model prompt — campaign instructions are explicitly wrapped in an `<untrusted_campaign_content>` boundary in the conversation policy builders specifically so the model is told to treat campaign text as goals/facts, not as instructions that override the permanent policy.
- Any new authentication or account-management code must resolve `organization_id` from the authenticated/database-backed context, never hardcode it. Preserve the signed-claim/database-match invariant implemented for [ADR-008](#).
- Passwords are hashed with `bcrypt` (via `auth_service.hash_password`/`verify_password`); never store or compare plaintext passwords anywhere, including in tests or seed scripts.

## Testing Principles

- This project uses Python's built-in `unittest`, run via `python -m unittest discover -s tests`. `pytest` is referenced in some historical documentation but is **not installed** in the virtual environment — do not assume it is available.
- Every behavioral bug fix ships with a new or updated test in the same change. This was followed without exception during this engineering pass: the campaign-automation fix added `tests/test_campaign_automation.py` (9 new tests covering `upsert_customer`, `update_sheet_status`, and `is_suppressed`); the Plivo language-menu feature added a test asserting the `<GetDigits>`/`<Play>` XML shape and that the fallback Record/Stream verbs still follow it.
- Database-touching service functions are tested with `unittest.mock.MagicMock`/`patch` against the connection/cursor object — there was no pre-existing pattern for this in the codebase before the campaign-automation tests; that pattern (a `_conn_with(...)` helper building a `MagicMock` with `cursor.fetchone.side_effect = [...]`) is now the established convention for new DB-mocked tests.
- Prompt/policy changes are checked for token budget, not just content, where a budget assertion already exists (`test_policy_token_budgets`, `test_static_policy_is_compact_and_enforces_short_spoken_tamil`) — a prompt edit that pushes a budget over its limit must be reworded to fit, not exempted by raising the limit casually.
- Run the full suite (`python -m unittest discover -s tests -q`) before calling any change complete; at last count this stands at 86 passing tests.

## Review Process

- No change to a live conversational prompt (`conversation_policy_service.py`) or to call-termination logic (`openai_realtime.py`'s `end_call` handling, `conversation_end.py`) should merge without a live or recorded test call exercising the changed path in both applicable languages, in addition to unit tests — unit tests alone cannot catch an LLM prompt-adherence regression like the "answered a whole turn in English mid-Tamil-call" incident this pass diagnosed and fixed.
- Any change to the do-not-call/suppression path (`is_suppressed`, its call sites) requires explicit review of **every** call site, not just the one being changed — this is a compliance-critical path where a missed call site (e.g., a new queue-advancement mechanism that forgets to check suppression) is a legal and reputational risk, not just a bug.
- Database schema changes must consider `organization_id` scoping from the outset, given the multi-tenant direction already encoded in the schema ([ADR-008](#)) — a new table without an `organization_id` column is a regression against that direction unless explicitly justified as genuinely global (e.g., a system-wide settings table).

## Documentation Standards

- Code comments explain **why**, never **what** — a well-named function and variable should make the "what" self-evident. Existing examples worth following: the `is_suppressed` docstring explaining *why* both the customer flag and the org-wide list are checked (duplicate customer records for the same phone number are possible), not just restating that it checks both.
- Do not leave TODO comments as a substitute for tracking work — track it in [TECHNICAL_DEBT.md](#) or [ENGINEERING_ROADMAP.md](#) instead, where it is visible and prioritized rather than silently rotting in a source file.
- When a decision is made that trades off one concern for another (e.g., accepting a fixed few seconds of call-start delay for the DTMF language menu in exchange for removing the campaign/language disconnect), record it as an ADR entry, not just a commit message — commit messages are not discoverable months later by an engineer trying to understand *why* something is the way it is.

## Naming Conventions

- Python: `snake_case` for functions/variables/modules, `PascalCase` for classes, `UPPER_SNAKE_CASE` for module-level constants and environment-variable-backed defaults (e.g., `TAMIL_TTS_SPEAKER`, `_LANGUAGE_PROMPT_TEXT`).
- Service functions that create-or-update should be named `upsert_*` (e.g., `upsert_customer`), not `save_*` or `create_or_update_*` — this convention should be followed for any future similar function.
- Boolean-returning check functions are named as a predicate (`is_suppressed`, `is_do_not_call_intent`, `is_short_acknowledgement`) — a function returning `bool` that isn't named this way should be renamed when touched.
- TypeScript/React: `PascalCase` for components, `camelCase` for functions/variables/hooks (hooks additionally prefixed `use*`), route-level components live under `src/pages/` named after the route they serve.
- Database columns: `snake_case`, booleans as `is_*`/`has_*` where practical (`is_active`, `is_suppressed`-equivalent `do_not_call`), foreign keys as `{referenced_table_singular}_id`.

## Repository Rules

- `.env` is never committed (`.gitignore`); `.env.example` documents every variable a fresh environment needs, including defaults and units where relevant (e.g., `OPENAI_TRANSCRIBE_AUDIO_INPUT_USD_PER_M=6`, explicitly documented as "verify against OpenAI's current pricing and override here if they drift").
- `credentials.json` (the Google service-account key) is never committed, is `.gitignore`d, and is resolved at runtime via `find_credentials_file()`'s search path (env var override, then a small set of candidate directories) rather than a hardcoded path.
- Generated/runtime artifacts (`*.mp3`, `*.wav`, `*.log`, `audio_cache/`, `logs/`, `app.db`) are `.gitignore`d — this includes the pre-rendered DTMF language-menu audio clip (`static/language_prompt.mp3`), which is regenerated on demand if missing rather than checked in.
- No secrets, tokens, or real customer phone numbers/PII belong in test fixtures, seed data, or example sheets — the seed script's default admin account and its documented password are for local bootstrap only and must be rotated before any non-local use.

## Folder Organization

```
app/
  api/         FastAPI routers — thin, delegate to services
  services/    Business logic, one concern per module
  services/telephony/   Provider-neutral telephony interface + Plivo implementation
  schemas/     Pydantic request/response models
  models/      Reference column declarations (not a live ORM session layer)
  database/    Connection/session helpers
  data/        Local knowledge-base assets (chroma vector store, uploads)
  utils/       Small, dependency-free helpers
src/
  pages/       Route-level screens
  components/  layout/, ui/, charts/ — reusable, presentation-focused
  hooks/       Reusable stateful logic
  api/         Typed HTTP client wrappers around the FastAPI backend
  types/       Shared TypeScript types
tests/         unittest test modules, one per service/module under test
migrations/    Schema migration scripts
docs/          Existing operational docs (e.g., Plivo migration inventory/checklist)
```

New code should slot into this structure rather than introduce a parallel one — e.g., a new provider integration belongs under `app/services/<concern>/`, following the `telephony/` pattern, not as a flat new top-level module if it has more than one file's worth of logic.

## Code Quality Expectations

- A pull request that fixes a bug is not "done" until: the root cause is identified and stated (not guessed), a regression test exists, the full test suite passes, and — for anything touching the live call path — the change has been exercised on at least one real or simulated call.
- Do not "fix" something that turns out, on investigation, not to be broken — report that finding honestly instead. This is not a hypothetical: a suspected telephony-cost overestimation bug was investigated by comparing stored costs against live Plivo CDR data across every completed call, found to match exactly, and reported as a non-issue rather than patched anyway.
- Do not add error handling for scenarios that cannot occur given the system's actual guarantees; do not add configuration flags for cases with no real second value yet. Both inflate the surface area future engineers must reason about for no present benefit.
