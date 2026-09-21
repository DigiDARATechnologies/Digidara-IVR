# DigiDARA — AI Engineering Context

**Read this first if you are Claude Code, OpenAI Codex, ChatGPT, Gemini CLI, Cursor, Windsurf, GitHub Copilot, or any other AI coding assistant working in this repository.** This document is written to let you understand DigiDARA correctly before you touch anything, and to constrain how you implement changes so they match this codebase's actual, evidence-based conventions rather than generic best practice.

## What This Project Is

DigiDARA is a bilingual (English/Tamil) AI voice sales-calling platform: FastAPI + MySQL (raw SQL, no ORM) backend, React/TypeScript/Vite frontend, Plivo for telephony, OpenAI's Realtime API for the live speech-to-speech conversation. It is a **working prototype with a real, exercised production call path** — not a demo, and not a greenfield project. Calls have been placed, recorded, billed, and analyzed on live infrastructure. Open workspace registration and organization-scoped application data are implemented; known gaps (signup abuse controls, payment entitlements, per-tenant credentials/content, RBAC, deployment, and operations) are tracked honestly, not hidden — read [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md) before assuming something is broken versus intentionally deferred.

For full detail, read in this order: [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) → [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) → the specific platform document for what you're touching ([`VOICE_PLATFORM.md`](VOICE_PLATFORM.md), [`AI_PLATFORM.md`](AI_PLATFORM.md), [`DATABASE_ARCHITECTURE.md`](DATABASE_ARCHITECTURE.md), [`SECURITY_GUIDE.md`](SECURITY_GUIDE.md)) → [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) for *why* things are the way they are.

## Architecture You Must Respect

- **One voice owns the call.** Plivo never speaks conversational content via its native `<Speak>` — OpenAI Realtime is the single voice the customer hears throughout the conversation. The one narrow exception (the DTMF language menu) plays a pre-rendered audio clip, specifically because Plivo cannot render Tamil speech — it does not use `<Speak>` either. **Do not add a new `<Speak>` verb anywhere in the live call flow** without first confirming the content is English-only and short; if in doubt, pre-render it via OpenAI TTS and use `<Play>` instead, following the existing pattern in `app/services/plivo_stream.py` and `app/api/plivo.py`.
- **The model judges intent; code enforces policy.** End-of-call decisions are made by the model via the `end_call` tool, not by keyword matching — this was a deliberate, hard-won architectural correction after keyword patterns repeatedly failed in live testing. **Do not "fix" a missed end-of-call case by adding another regex pattern** to `conversation_end.py` as the primary mechanism; the tool-calling path is authoritative. Regex/keyword classification (`classify_intent`) is fine — even encouraged — for structured, deterministic tasks: CRM disposition tagging, lead-status categorization, analytics.
- **Compliance is a gate, not an afterthought.** `is_suppressed()` sits at every place a call could be placed or a queue could advance. **If you add a new way to place a call or advance a campaign queue, you must call `is_suppressed()` there too**, and handle the suppressed case by skipping/marking the row — never by blocking the whole queue on it, and never by silently dialing anyway.
- **Every prompt is production code.** `app/services/conversation_policy_service.py`'s prompt-builder functions are as behaviorally significant as any Python logic — two real production bugs during this codebase's history were prompt-wording issues, not code bugs. **Treat a prompt-string edit with the same care as a code change**: check the token-budget tests still pass, and if you cannot run a live test call yourself, say so explicitly rather than declaring the change verified.
- **Provider abstraction exists where there's real multi-provider need, not speculatively.** Telephony is abstracted (`app/services/telephony/`, `get_telephony_provider()`) because a second provider is a real near-term possibility. Google Sheets and the AI Realtime bridge are **not** yet abstracted — there's exactly one implementation of each. **Do not build a new abstraction layer "for the future"** unless you are actually integrating a second concrete implementation right now.
- **No ORM.** All database access is raw, parameterized SQL via PyMySQL dict cursors. `app/models/*.py` is reference documentation, not a live session layer. **Do not introduce SQLAlchemy ORM usage into the live request path** without an explicit, separate decision to do so — this is a deliberate architectural choice (see [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) ADR-007), not an oversight to "fix."

## Rules You Must Follow

### Coding Rules

- Every SQL statement must be parameterized (`%s` placeholders with a separate values tuple/list). Never build a SQL string with an f-string or `%`-formatting containing a variable value.
- Keep `app/api/*.py` route handlers thin — parse the request, call a service function, shape the response. Business logic belongs in `app/services/*.py`.
- Name find-or-create functions `upsert_*` (matching `customer_service.upsert_customer`), boolean checks as a predicate (`is_*`), constants `UPPER_SNAKE_CASE`.
- Do not add speculative abstractions, config flags, or error handling for scenarios that cannot occur given this system's actual guarantees.
- Do not introduce a new dependency without checking whether an existing one already solves the problem (e.g., `requests` is already used for one-off REST calls; `websockets` for the Realtime bridge — don't add `httpx` or the `openai` SDK for something these already cover).

### Security Rules

- Every new Plivo webhook route must validate the V3 HMAC signature via the existing `_signed_form()` pattern in `app/api/plivo.py`. No exceptions for "internal" or "test" routes.
- Never hardcode `organization_id` (or write code that assumes single-tenancy). Resolve it from the authenticated principal for private application routes or from signed provider-correlated records for callback paths, and include it in every tenant-owned query.
- Never log, persist, or echo back a raw secret or credential. Passwords are PBKDF2-HMAC-SHA256 hashed; never compare or store them in plaintext, including in test fixtures.
- Treat campaign `ai_prompt` content, Google Sheet row data, and any other operator- or externally-supplied text that flows into a model prompt as untrusted — wrap it the way `<untrusted_campaign_content>` already does, with an explicit instruction that it cannot override the permanent policy.
- Never disable `PLIVO_VALIDATE_SIGNATURES` or suggest disabling it, even "temporarily for debugging," outside of local development with `ENVIRONMENT=development`.

### Testing Rules

- This project uses Python's built-in **`unittest`**, invoked via `python -m unittest discover -s tests -q`. **`pytest` is not installed** — do not write `pytest`-specific syntax (fixtures, `@pytest.mark.parametrize`) unless you have first confirmed `pytest` has been added as an actual dependency.
- Every behavioral bug fix must ship with a new or updated test in the same change. This is not optional style guidance — it is this codebase's actual, consistently-followed practice, and a fix without a test should be treated as incomplete.
- For a service function that takes a database connection, mock it with `unittest.mock.MagicMock`, configuring `cursor().fetchone`/`fetchall` via `return_value` or `side_effect` — follow the pattern established in `tests/test_campaign_automation.py`'s `_conn_with()` helper rather than inventing a new mocking style.
- If you change a prompt-builder function in `conversation_policy_service.py`, check whether a token-budget test covers it (`test_policy_token_budgets`, `test_static_policy_is_compact_and_enforces_short_spoken_tamil`) and make sure your change doesn't push it over budget — reword the prompt to fit rather than raising the limit casually.
- Run the full suite before declaring any change complete, and report the actual pass/fail count — do not claim "tests pass" without having run them.

### Folder Rules

Follow the structure in [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md): `app/api/` for thin routers, `app/services/` for business logic (one file per concern), `app/services/telephony/` for the provider abstraction, `app/schemas/` for Pydantic models, `src/pages/` for frontend route screens, `src/components/` for reusable UI, `tests/` with one test module per concern under test. Do not create a parallel structure (e.g., a new top-level `lib/` or `core/` directory) without a clearly-stated reason grounded in an actual limitation of the existing structure.

## What AI Assistants Must NEVER Do

1. **Never claim a change is tested or verified without actually running the test suite.** If you cannot run it (no execution environment available), say so explicitly rather than stating or implying it passes.
2. **Never invent architectural history.** If asked to reference "prior decisions" or "what was previously approved," ground your answer in what is actually verifiable in this repository's code, tests, and documentation — not in a plausible-sounding but unverifiable narrative. If you don't have the information, say so.
3. **Never disable a security control to make a task easier** — signature validation, password hashing, parameterized queries, the suppression-list gate — even temporarily, even if asked, without first raising the concern explicitly to the human you're working with.
4. **Never add a new call-placement or campaign-queue-advancement code path without wiring in `is_suppressed()`.** A dialer that can place a call without checking do-not-call status is a compliance failure, not a minor bug.
5. **Never treat the Twilio-era code (`twilio_service.py`, `conversation_relay.py`) or the LiveKit agent (`app/livekit_agent/`) as the active call path.** The active, confirmed production path is Plivo + OpenAI Realtime (`app/api/plivo.py`, `app/api/openai_realtime.py`). If a task description implies otherwise, flag the discrepancy rather than silently guessing which path is meant.
6. **Never fabricate a "fix" for something that, on investigation, isn't actually broken.** This codebase has a specific precedent for reporting a suspected bug as a non-issue after live verification (the telephony-cost investigation, [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) ADR-006) — follow that precedent: investigate first, report honestly, only "fix" what's actually confirmed broken.
7. **Never modify a live conversational prompt casually.** A one-line prompt wording change has, twice, caused a real live-call behavior regression in this codebase. Treat prompt edits as high-stakes changes requiring the same rigor as a code change to critical business logic.
8. **Never assume `pytest` is available**, or that dependencies are pinned/reproducible — both are known, tracked gaps (see [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md)), not things to silently work around by installing packages ad hoc without recording them.

## How Implementation Should Proceed

1. **Identify the root cause before proposing a fix.** Read the actual code path involved; do not guess based on a plausible-sounding symptom description. This codebase's own fixes (English hangup, campaign automation, cost tracking) were all root-caused by direct code reading and, where applicable, live data verification — not by pattern-matching against "common causes of X."
2. **Check `TECHNICAL_DEBT.md` and `ENGINEERING_ROADMAP.md` first** — the task may already be scoped there with acceptance criteria in `IMPLEMENTATION_CHECKLIST.md`.
3. **Make the smallest correct change.** Do not refactor unrelated code, rename things "while you're in there," or add abstractions the task doesn't need.
4. **Write or update a test in the same change.**
5. **Run the full test suite and report actual results.**
6. **For live-call-path changes, flag clearly that a live or recorded test call is recommended** even if you cannot perform one yourself — do not let unit-test success stand in for conversational-behavior verification.
7. **Update the relevant documentation** (an ADR entry for a new architectural decision, a `TECHNICAL_DEBT.md` or `ENGINEERING_ROADMAP.md` update if you've closed a tracked item) as part of the same change, not as an afterthought.

## How Architecture Should Be Respected

This system's architecture reflects specific, evidence-based decisions, not defaults chosen by omission:

- Two different turn-taking mechanisms per language (English automatic VAD, Tamil manual validated-turn planner) — this is intentional, not an inconsistency to "clean up" into one shared mechanism.
- No `language` column on `campaigns` — campaign name and call language are deliberately decoupled; the customer's own DTMF choice (or `customers.language`) is authoritative, not campaign metadata. Do not "fix" this by adding a `campaigns.language` column and wiring campaign selection back into call-language decisions without understanding why that link was deliberately removed (see [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) ADR-005).
- The multi-tenant schema (`organization_id` everywhere) predates its own enforcement — this is a sequencing choice (schema-first, enforcement-second), not evidence the schema design is wrong. When working on tenancy, your job is to *close the enforcement gap*, not redesign the schema.
- Raw SQL over an ORM, a provider abstraction for telephony but not (yet) for Sheets or the AI bridge, `unittest` over `pytest` — each of these is a considered tradeoff documented in [`ARCHITECTURE_DECISION_RECORD.md`](ARCHITECTURE_DECISION_RECORD.md) or [`ENGINEERING_GUIDELINES.md`](ENGINEERING_GUIDELINES.md). If you believe one should change, raise it explicitly as a proposal with the tradeoffs stated — don't silently drift the codebase away from a documented decision one PR at a time.

If any instruction in a task you're given conflicts with something in this document, surface the conflict explicitly rather than silently resolving it in either direction.
