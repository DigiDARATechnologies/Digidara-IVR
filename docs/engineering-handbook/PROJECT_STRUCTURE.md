# DigiDARA — Project Structure

## Repository Root

```
DigiDARA-AI-VOICE-AGENT/
  app/                   Python backend (FastAPI)
  src/                   React/TypeScript frontend
  tests/                 Python unittest suite
  migrations/            Database schema migration scripts
  docs/                  Existing operational docs (Plivo migration inventory/checklist)
  static/                Runtime-generated static assets (e.g., the pre-rendered DTMF language prompt)
  schema.sql             Baseline database schema
  seed.py                Local admin-account seeding script
  package.json / vite.config.ts / tsconfig*.json / tailwind.config.js / postcss.config.js
                         Frontend build tooling configuration
  .env.example           Documented environment variables (no real secrets)
  .env                   Real local secrets (never committed)
  credentials.json       Google service-account key, when present (never committed)
  README.md              Project introduction (see README.md for the current version)
  IMPLEMENTATION_REPORT.md
                         Prior engineering report on the bilingual English/Tamil realtime
                         refactor — retained as historical record of that specific change
```

## `app/` — Backend

```
app/
  main.py                FastAPI application entrypoint, router mounting
  api/                    HTTP/WebSocket routers — thin, delegate to services
    auth.py                Authentication: bootstrap-admin, login, admin user creation
    call.py                Single-call initiation, /calls/run-sheet (bulk campaign entry),
                            legacy-adjacent voice_welcome/voice_respond handlers
    campaign.py            Campaign CRUD
    customer.py            Customer/CRM CRUD
    plivo.py               All Plivo webhooks: /answer, /language-select, /ring, /hangup,
                            /recording, /stream-status, /inbound
    openai_realtime.py      The /ws/plivo/media bridge — Plivo audio stream <-> OpenAI Realtime
    conversation_relay.py   Twilio-era voice relay (not the active production path)
    insights.py             Analytics/dashboard queries
    lead_score.py           Lead scoring endpoints
    rag.py                  Retrieval-augmented endpoints for the in-app assistant
    chat.py                 In-app assistant chat surface
    webhook.py              Generic webhook handling (non-Plivo)
  services/                Business logic — one concern per module
    telephony_service.py      Outbound call orchestration, suppression enforcement,
                              campaign queue advancement (start_outbound_call, is_suppressed,
                              trigger_next_queued_call)
    telephony/                Provider-neutral telephony interface
      plivo_provider.py         Plivo SDK implementation (create_call, get_call, terminate_call,
                                validate_callback)
      status.py                 Provider-status-to-product-status mapping
    plivo_stream.py           Plivo Audio Streaming protocol helpers + XML builders
                              (build_answer_xml, build_language_prompt_xml, stream_token)
    customer_service.py       Customer CRUD + upsert_customer (sheet-driven find-or-create)
    campaign_service.py       Campaign CRUD
    call_log_service.py       Call lifecycle state transitions, idempotent callback binding
    conversation_policy_service.py
                              System-prompt builders (English/Tamil), classify_intent,
                              knowledge-context formatting
    conversation_end.py       Regex-based explicit end-of-call phrase detection
    conversation_service.py   Conversation/transcript persistence helpers
    tamil_conversation_service.py
                              Tamil-specific conversation architecture support
    tamil_register.py         Tamil register/style matching helpers
    realtime_input_gate.py    Turn validation (duration/RMS/voiced-frame thresholds)
    realtime_turns.py         Turn-sequencing helpers
    google_sheets_service.py  Sheet read (auth + public-CSV fallback), header normalization,
                              write-back (update_sheet_feedback / update_sheet_status)
    memory_service.py         Cross-call customer memory (customer_memory table)
    lead_extraction_service.py / lead_scoring.py
                              Structured lead-qualification extraction and scoring
    knowledge_base.py / knowledge_base_ta.py / knowledge_ta.txt
                              Approved knowledge content per language, Tamil BM25 index source
    rag_service.py            Retrieval for the in-app assistant surface
    auth_service.py            JWT issuance/verification, bcrypt password hashing
    call_summary.py            Post-call summary generation
    calendar_service.py        Scheduling/follow-up support
    audio_utils.py             Audio format helpers
    sales_playbook.py          Sales-flow reference content
    elevenlabs_service.py / gemini_service.py / groq_service.py / sarvam_service.py
                              Alternative TTS/LLM provider integrations — not wired into the
                              active Plivo + OpenAI Realtime production path; retained from
                              earlier iterations or evaluated for future use
    twilio_service.py          Twilio-era voice pipeline (not the active production path)
    knowledge_uploaded_update.py
                              Knowledge-base document ingestion support
  schemas/                  Pydantic request/response models
    customer.py, campaign.py, call.py, call_log.py, chat.py, lead_score.py
  models/                   Reference column declarations (documentation, not a live ORM layer)
    customer.py, campaign.py, call_logs.py, conversation.py
  database/                 Connection/session helpers (get_db, get_db_connection)
  data/                     Local knowledge-base assets
    chroma/                   Vector store data, if/when used by rag_service.py
    kb_uploads/               Uploaded knowledge documents
  livekit_agent/            LiveKit-based agent code — an alternative/exploratory voice
                            integration path, not the active Plivo + OpenAI Realtime path
  utils/                    Small, dependency-free helper functions
```

## `src/` — Frontend

```
src/
  pages/                  Route-level screens: Overview, Customers, Campaigns, Live Calls,
                          Bulk Calling, Leads, Analytics, Knowledge Base, Playground,
                          Integrations, Team & Roles, Usage & Billing
  components/
    layout/                 App shell: sidebar, top bar, navigation
    ui/                      Reusable presentational primitives (buttons, cards, forms)
    charts/                  Recharts-based visualization components
  hooks/                  Reusable stateful/data-fetching logic (paired with react-query)
  api/                    Typed HTTP client wrappers around the FastAPI backend (axios)
  types/                  Shared TypeScript types/interfaces
  styles/                 Global styles / Tailwind entrypoints
```

## `tests/` — Test Suite

One test module per concern under test, mirroring the service it exercises (e.g., `test_campaign_automation.py` for `customer_service.upsert_customer` / `google_sheets_service.update_sheet_status` / `telephony_service.is_suppressed`; `test_plivo_migration.py` for `plivo_stream.py` and Plivo protocol/status logic; `test_conversation_end.py` / `test_conversation_policy_service.py` / `test_tamil_conversation_service.py` for conversation logic and prompt-token budgets). New tests should follow this same one-module-per-concern pattern rather than accumulating into a small number of large, unfocused test files.

## Module Ownership & Dependencies

- `api/*` depends on `services/*` and `schemas/*`; it must not contain business logic or raw SQL beyond simple existence/authorization checks delegated from a service.
- `services/*` depends on `database/`, `schemas/*` (for constructing typed payloads passed to CRUD functions), and, for telephony/AI-specific services, the relevant external SDK or protocol module (`plivo` SDK inside `telephony/plivo_provider.py` only; `websockets` inside `api/openai_realtime.py`).
- `services/telephony/*` must never be imported directly by `api/*` — all call orchestration goes through `telephony_service.py`, which is the only consumer of `get_telephony_provider()`.
- `models/*` is a reference/documentation layer; no other module should depend on it for runtime behavior, since it is not a live ORM session layer.
- Frontend `pages/*` depends on `hooks/*` and `api/*`; it should not call `axios`/fetch directly — all backend communication goes through the typed `api/` client layer so response shapes are defined once, in `types/`, and reused.

New modules should be placed according to this structure rather than introducing a parallel organization — see [ENGINEERING_GUIDELINES.md](#) Folder Organization for the enforcement rule.
