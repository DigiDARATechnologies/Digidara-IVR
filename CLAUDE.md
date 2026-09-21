# CLAUDE.md

Guidance for Claude Code (and any AI coding assistant) working in this repository.

## What this project is

DigiDARA is a bilingual (English/Tamil) AI voice sales-calling platform: FastAPI + MySQL (raw SQL, no ORM) backend, React/TypeScript/Vite frontend, Plivo for telephony, OpenAI's Realtime API for the live speech-to-speech conversation. It is a **working prototype with a real, exercised production call path** — calls have been placed, recorded, billed, and analyzed on live infrastructure. It is not a demo and not greenfield.

## Read this first

Full engineering documentation lives in [`docs/engineering-handbook/`](docs/engineering-handbook/MASTER_INDEX.md). Before making any non-trivial change, read **[`docs/engineering-handbook/AI_ENGINEERING_CONTEXT.md`](docs/engineering-handbook/AI_ENGINEERING_CONTEXT.md)** — it is written specifically for AI coding assistants and covers what this codebase's architecture requires you to respect, rules you must follow (coding/security/testing/folder), and things you must never do.

For anything deeper, use the index to find the right doc — architecture, database schema, voice platform, AI/prompt platform, security posture, known technical debt, and the roadmap all have dedicated documents there. Don't guess at the schema or the call flow when a document already describes it — check it first, then verify against the actual code if anything seems off, since the docs are a snapshot and can drift from the code over time.

## The essentials, if you read nothing else

- **The active call path is Plivo + OpenAI Realtime** (`app/api/plivo.py`, `app/api/openai_realtime.py`). `app/services/twilio_service.py`, `app/api/conversation_relay.py`, and `app/livekit_agent/` are retained legacy/exploratory code, not the production path — don't extend them assuming otherwise.
- **No ORM.** All database access is raw, parameterized SQL via PyMySQL. Every SQL value goes through a `%s` placeholder — never an f-string or `%`-formatted value.
- **The model judges call-termination intent via an `end_call` tool call**, not keyword matching. Regex/keyword classification (`conversation_end.py`, `classify_intent`) exists for structured CRM tagging, not as the terminal gate on ending a call.
- **Do-not-call/suppression (`is_suppressed`) must be checked at every place a call can be placed or a campaign queue can advance.** If you add a new dialing or queue-advancement path, wire this in — this is a compliance-critical gate, not a nice-to-have.
- **Prompts are production code.** `app/services/conversation_policy_service.py`'s prompt builders have caused real live-call behavior regressions before. Treat prompt edits with the same rigor as logic changes, and check the token-budget tests (`test_policy_token_budgets`, `test_static_policy_is_compact_and_enforces_short_spoken_tamil`) still pass.
- **Tests are `unittest`, not `pytest`** (`pytest` is not installed). Run `python -m unittest discover -s tests -q`. Every behavioral bug fix ships with a new or updated test in the same change — this is the actual, consistently-followed practice in this codebase, not aspirational.
- **Known, tracked gaps** — don't rediscover these as if new, and don't "fix" them casually without reading the fuller context in `TECHNICAL_DEBT.md`: authenticated tenant data, Plivo/OpenAI/CRM credentials, and live-call organization knowledge are tenant-scoped, but signup lacks abuse controls and payment entitlements, Google Sheets credentials remain environment-level, the retained legacy knowledge surface is restricted rather than tenant-aware, and authorization is admin-only. Account lockout, the pinned dependency manifest, and CI are implemented.
- **Investigate before "fixing."** If something looks broken, trace it to the actual root cause first. This codebase has precedent for investigating a suspected bug and honestly reporting it as a non-issue when the evidence didn't support it — don't patch around a symptom you haven't actually root-caused.

## Documentation index

See [`docs/engineering-handbook/MASTER_INDEX.md`](docs/engineering-handbook/MASTER_INDEX.md) for the full list with purpose/audience/read-when guidance for each document.
