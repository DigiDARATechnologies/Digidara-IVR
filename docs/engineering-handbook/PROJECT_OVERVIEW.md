# DigiDARA — Project Overview

## Business Vision

DigiDARA is an AI voice sales-calling platform built for education and training providers who run outbound enrollment campaigns to leads sourced from marketing forms, walk-ins, and referral sheets. The business problem it solves is simple to state and hard to execute well: a counselling team has a list of hundreds or thousands of enquiries, a small number of human counsellors, and a narrow window before a lead goes cold. DigiDARA replaces the first outbound touch — the "are you still interested, let me tell you about the course, when can you start" conversation — with an AI voice agent that calls the lead, speaks in the lead's preferred language, answers course questions from an approved knowledge base, and either books a next step or records a clean disposition (not interested, callback requested, do-not-call) back into the CRM and the source spreadsheet.

The commercial thesis is that outbound lead qualification is a volume problem before it is a quality problem. A human counsellor can make perhaps 40–60 calls a day; an AI voice agent, run correctly, can attempt hundreds, filter out the leads who were never going to answer or were never interested, and hand qualified, warm leads to the human team for the close. The product is therefore positioned as a **pre-sales qualification layer**, not a replacement for human closers.

## Product Vision

DigiDARA is a bilingual (English / Tamil) real-time voice agent that:

- Places outbound calls through a telephony provider (Plivo today, behind a provider-neutral interface).
- Carries on a natural, low-latency, speech-to-speech conversation using OpenAI's Realtime API rather than a legacy record → transcribe → synthesize pipeline.
- Lets the customer choose their spoken language at the start of the call via a DTMF menu, rather than assuming language from campaign metadata or a spreadsheet column.
- Grounds its answers in an approved knowledge base per language, so it does not invent fees, dates, or placement guarantees.
- Judges for itself, from the flow of the conversation, when the customer wants the call to end — using an LLM tool call rather than brittle keyword matching — and closes the call gracefully.
- Automatically works through a Google Sheet of leads, dialing one at a time, skipping numbers on the do-not-call list, and writing status back to the sheet as it progresses.
- Tracks the true cost of every call (telephony minutes plus Realtime token usage, input and output, audio and text, including the separate transcription model) so unit economics are visible per call, per campaign, per organization.

The longer-term product vision is a platform, not a single tool: multiple organizations (tenants) running multiple campaigns, in multiple languages, with role-based access for their own counselling teams, each organization's credentials and data isolated from every other's. The database schema already reflects this direction — every core table (`customers`, `campaigns`, `call_logs`, `suppression_list`, `app_users`, `api_credentials`, `audit_logs`) carries an `organization_id` column today. What remains is enforcing that boundary consistently in application code (see [ARCHITECTURE_DECISION_RECORD.md](#) and [SECURITY_GUIDE.md](#)), not redesigning the data model to support it.

## Current Project Status

DigiDARA is a **working prototype with a real, in-progress production path**, not a pure concept demo. Concretely, as of this writing:

- A live outbound call can be placed from the UI, ring a real phone over Plivo, and hold a full bilingual conversation via OpenAI Realtime, with the call recorded, billed, and logged.
- The bulk-calling feature reads a Google Sheet, creates or updates CRM customer records, checks do-not-call suppression before dialing, places the call, and writes call status back to the sheet — this loop was broken (two missing functions and a parameter-name bug) and has been fixed and unit-tested during the current engineering pass.
- Call termination is judged by the model itself via an `end_call` tool the AI can invoke mid-turn, replacing an earlier keyword-matching approach that missed many real phrasings, in both English and Tamil.
- Cost telemetry now accounts for the separate ASR transcription model billing that was previously untracked, alongside the existing Realtime token and Plivo minute costs.
- A DTMF language-selection menu ("Press 1 for English, Press 2 for Tamil") now runs at the start of every outbound call, so the customer's own choice — not the sheet or campaign — decides the call language; Plivo's native speech synthesis cannot render Tamil, so the menu audio is pre-rendered once via OpenAI TTS and played back rather than spoken live by the telephony provider.
- Authentication includes JWT issue/verify, PBKDF2-HMAC-SHA256 password hashing, configurable consecutive-failure account lockout, open workspace plus first-admin registration, workspace-aware login, a signed organization claim checked against the active user's database organization, and organization-scoped access to the audited tenant-owned data paths.
- Backend direct dependencies are pinned in `app/requirements.txt`, and GitHub Actions runs a clean Python 3.11 install, the backend regression suite, `npm ci`, and the frontend production build on every push and pull request.
- Local development relies on ephemeral Cloudflare Quick Tunnels for the public webhook URL Plivo calls back to, which is adequate for iteration but not for a stable staging/production environment.

In short: **the core voice product works end-to-end and has been exercised on live calls.** The gaps that remain are in tenancy enforcement, dependency and deployment hygiene, and the breadth of the knowledge base and analytics layers — not in the fundamental voice architecture.

## Future Roadmap

The roadmap below is the practical, evidence-based path from the current prototype to a commercial multi-tenant SaaS product. Full detail, sequencing, and acceptance criteria live in [ENGINEERING_ROADMAP.md](#) and [IMPLEMENTATION_CHECKLIST.md](#); this is the summary.

1. **Harden the prototype** — add login rate limiting and replace the dev-only Cloudflare tunnel with a stable ingress for any non-local environment. Pinned dependencies, CI, private-route authentication coverage, account lockout, and audited organization-scoped data access are complete.
2. **Prove the campaign loop at real volume** — run bulk campaigns against real lead sheets (not throwaway test rows), monitor the do-not-call gate and sheet-write-back under load, and confirm Google service-account credentials are provisioned per environment rather than a single developer's local file.
3. **Deepen the AI platform** — expand the approved knowledge base coverage, add automated conversation-quality evaluation (not just cost/latency telemetry), and formalize the prompt-change review process now that prompt edits have already changed live call behavior twice during this engineering pass.
4. **Multi-tenant SaaS** — build on the enforced application data boundary and open workspace registration with payment entitlements, signup abuse controls, encrypted per-tenant provider credentials, role-based access beyond the current binary admin flag, and tenant-specific knowledge content.
5. **Enterprise readiness** — audit logging coverage across all sensitive actions (the `audit_logs` table exists and is used for admin-account creation today, not yet for calling, customer data export, or credential rotation), data-retention automation keyed off `organizations.data_retention_days` (present in schema, not yet enforced by a job), and formal incident-response processes.
6. **Platform expansion** — additional languages beyond English/Tamil, additional telephony and LLM providers behind the existing provider-neutral interfaces (`app/services/telephony/`, and the Realtime abstraction), and a public API for CRM integrations.

This sequence intentionally treats *tenancy enforcement* as the highest-leverage item before *feature breadth*: adding more languages, providers, or campaign types to a system with an unenforced organization boundary multiplies the blast radius of that gap rather than fixing it.

## Technology Stack

**Backend**
- Python 3, FastAPI (`fastapi==0.141.1`), Uvicorn ASGI server.
- MySQL 8, accessed via raw `PyMySQL` — there is no ORM in the live request path; queries are hand-written SQL against dict-cursor connections.
- Pydantic v2 for request/response schema validation.
- `PyJWT` + `bcrypt` for authentication tokens and password hashing.
- `websockets` for the bidirectional OpenAI Realtime API connection.
- `plivo` SDK for outbound call creation, and Plivo's Audio Streaming (WebSocket) protocol for the live audio path.
- `gspread` + `google-auth` for Google Sheets read/write (campaign automation), with a public CSV-export fallback when no service-account `credentials.json` is present.
- `requests` for one-off REST calls (e.g., OpenAI's TTS `audio/speech` endpoint used to pre-render the DTMF language-menu prompt).

**Frontend**
- React 18 + TypeScript, built with Vite.
- `@tanstack/react-query` for server state, `axios` for HTTP, `react-router-dom` for routing.
- Tailwind CSS for styling, `recharts` for analytics charts, `lucide-react` for icons.

**Telephony & Voice**
- Plivo: outbound Calls API, signed (V3 HMAC) webhooks, bidirectional Audio Streaming, CDR-based billing reconciliation.
- OpenAI Realtime API (WebSocket, speech-to-speech) as the conversational engine for both English and Tamil.
- A provider abstraction layer (`app/services/telephony/`) so Plivo can be swapped or joined by another carrier without touching call orchestration logic.

**Infrastructure (current, development-grade)**
- Local MySQL instance.
- Cloudflare Quick Tunnels (`trycloudflare.com`) for exposing the local backend to Plivo's webhooks during development — ephemeral by design, not a production ingress.
- No containerization, automated deployment pipeline, or infrastructure-as-code exists yet; GitHub Actions does run the backend tests and locked frontend build. See [DEPLOYMENT_GUIDE.md](#) for the target state.

## Architecture Philosophy

Three principles run through every design decision in this codebase, whether or not they have been written down before:

1. **One voice owns the call.** The provider (Plivo) never speaks natural conversational content — `<Speak>` is deliberately absent from the main call flow so that OpenAI Realtime is the single, consistent voice and personality the customer hears. The one exception — the DTMF language menu — plays a pre-rendered clip rather than falling back to provider TTS, specifically because Plivo's native speech synthesis has no Tamil voice.
2. **The model judges intent; code enforces policy.** Whether a customer wants to end the call is a judgment call the LLM makes via a tool call (`end_call`) informed by conversational nuance in either language — not a regex over transcript text. Regex and keyword matching remain in the codebase as a defense-in-depth layer and for structured analytics (e.g., `classify_intent` for lead-status tagging), but the terminal decision to end a call is the model's, not a keyword list's.
3. **Compliance is a gate, not an afterthought.** Do-not-call and suppression checks (`is_suppressed`) sit at the single choke point where every outbound call is placed (`start_outbound_call`), and are re-checked at every queue-advancement site (single-call trigger and bulk-sheet trigger) so that a suppressed lead can never be silently skipped in a way that stalls the rest of the queue, nor silently dialed.

## Engineering Principles

- **Fix the root cause, not the symptom.** Recent examples in this codebase: a "the AI says goodbye but the call never hangs up" bug was traced to a hangup path gated behind `if language == "tamil"` that silently never fired for English calls, not patched around; a cost-dashboard discrepancy was traced to a genuinely missing transcription-cost term in the billing formula, and a separate suspected telephony-cost bug was investigated and found, on live data, not to exist — that finding was reported honestly rather than "fixed" anyway.
- **Prefer model judgment over brittle pattern matching for user intent**, and prefer pattern matching only for cases where determinism and auditability matter more than nuance (billing math, suppression checks, database writes).
- **No dependency should be silently assumed.** Where the system degrades gracefully (e.g., Google Sheets read falls back to public CSV export when no service-account credentials exist), that fallback and its limitations should be explicit and documented, not discovered by a confused operator days later — the write-back path has no such fallback and fails loudly (`raise RuntimeError`) rather than silently dropping data.
- **Tests are the source of truth for behavior, not comments.** The test suite uses Python's built-in `unittest` (not `pytest`, which is not installed) and currently stands at 102 passing tests covering authentication coverage, conversation-end intent classification, Plivo XML generation, campaign automation, inactivity handling, and Realtime policy behavior. Every behavioral bug fix during this engineering pass was paired with a new or updated test before being called done.
- **Every prompt change is a behavior change.** Two live incidents during this engineering pass were traced directly to conversational system-prompt wording (an over-broad "switch to English" instruction, and Plivo's inability to speak Tamil natively) — prompts are treated with the same review discipline as code, because in this system they *are* the code that decides what the customer hears.
