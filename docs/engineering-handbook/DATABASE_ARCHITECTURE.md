# DigiDARA — Database Architecture

## Overview

DigiDARA runs on MySQL 8, accessed exclusively through `PyMySQL` with dict cursors and hand-written, parameterized SQL (see [ARCHITECTURE_DECISION_RECORD.md](#) ADR-007 for the rationale). There is no ORM session layer in the live request path; `app/models/*.py` contains lightweight column declarations that document the schema rather than mediate access to it. Nineteen tables exist today, grouped below by concern.

## Current Schema

### Identity & Tenancy

**`organizations`** — `id`, `name`, `slug` (unique), `status`, `plan_code`, `monthly_call_limit`, `data_retention_days`, timestamps. The tenancy root. `monthly_call_limit` and `data_retention_days` exist as quota/retention fields with no enforcement job wired to them yet (see [ENGINEERING_ROADMAP.md](#) Epic E/G).

**`app_users`** — `id`, `organization_id` (FK), `email`, `password_hash`, `full_name`, `role_code`, `is_active`, `mfa_enabled`, `failed_login_attempts`, `locked_until`, `last_login_at`, timestamps. `(organization_id, email)` is unique, so the same email can intentionally exist in two workspaces. Login uses `organizations.slug` to select the correct account before password verification. `role_code` is a flat string today (`"admin"` is the only value the code branches on); account lockout uses `failed_login_attempts` and `locked_until`, while MFA remains unimplemented.

**`user_sessions`** — `id`, `user_id` (FK), `refresh_token_hash` (unique, sha256-length char(64)), `expires_at`, `revoked_at`, `ip_address`, `user_agent`, `created_at`. Designed to support refresh-token rotation and remote session revocation; confirm this table is actually read/written on every login/logout before relying on it for session revocation guarantees.

**`api_credentials`** — `id`, `organization_id` (FK), `provider`, `credential_ciphertext`, `key_version`, `last_four`, `rotated_at`, timestamps. Designed for per-tenant, encrypted third-party credentials with key-rotation support (`key_version`). Not yet wired into active use; today's provider credentials live in `.env` (see [SECURITY_GUIDE.md](#)).

### CRM & Compliance

**`customers`** — `id`, `organization_id` (FK), `name`, `email` (unique within an organization via `(organization_id, email)` — used as the natural key for sheet-sourced rows via a synthesized `{phone_digits}@example.com` address), `phone`, `language`, `investigated_course`, `internship_or_course`, `course_duration`, `sheet_url`, `sheet_row`, `customer_status`, `is_active`, `consent_status`, `consent_at`, `consent_source`, `do_not_call`, `assigned_user_id` (FK), `deleted_at` (soft delete), timestamps. `language` defaults such that an empty/invalid value resolves to `"english"` in application code (`app/api/call.py`), not at the database level.

**`suppression_list`** — `id`, `organization_id` (FK), `phone_hash` (char(64), sha256 of digits-only phone), `reason`, `source`, `created_at`. Deliberately keyed on a phone hash rather than a customer FK, so a suppression can apply org-wide even across multiple customer records that happen to share a phone number — this is exactly the scenario `is_suppressed()` checks both the per-customer flag and this table to cover.

**`followup_reminders`** — `id`, `customer_id` (FK), `campaign_id` (FK), `source_call_log_id` (FK), `reminder_type`, `scheduled_at`, `status`, `notes`, `completed_at`, timestamps.

**`customer_memory`** — `id`, `customer_id` (FK, unique — one row per customer), `name`, `intent`, `previous_questions`, `lead_status`, `summary`, `preferred_language`, `total_calls`, `successful_calls`, `last_contacted_at`, timestamps. This is the durable, cross-call memory injected into future session instructions (`compact_customer_memory`), distinct from `conversations` (the raw per-turn transcript log).

### Campaigns & Calls

**`campaigns`** — `id`, `organization_id` (FK), `campaign_name`, `objective`, `ai_prompt` (longtext — this is the untrusted content wrapped in `<untrusted_campaign_content>` at prompt-build time), `status`, timestamps. Notably has **no `language` column** — campaign language implication in a name like "... - Tamil" is a human convention only; the actual per-call language is resolved from `customers.language` (or, since the DTMF menu feature, the customer's own live keypress), never from the campaign row. See [ARCHITECTURE_DECISION_RECORD.md](#) ADR-005.

**`call_logs`** — the largest table, one row per call attempt. Identity/provider fields (`call_sid`, `provider`, `provider_request_id`, `provider_call_id`, `correlation_id` — unique, generated per attempt and used to bind async provider webhooks back to the right row); status fields (`status`, `call_status`, `provider_status`, `stream_status`); language/model fields (`language`, `realtime_model`, `transcription_model`, `realtime_voice`, `voice_style_profile`, `knowledge_profile`, `conversation_profile`, `turn_gate_profile` — these last four record *which* prompt/turn-handling configuration served the call, valuable for A/B-style historical analysis); cost fields (`estimated_openai_cost_usd`, `estimated_twilio_cost_usd` — a legacy-named column from the pre-Plivo era, `estimated_telephony_cost_usd` — the actual live-reconciled Plivo cost, `input_audio_tokens`, `output_audio_tokens`, `input_text_tokens`, `output_text_tokens`); quality/diagnostic fields (`total_turns`, `interruption_count`, `false_turn_count`, latency percentile fields, `stt_confidence_avg`); disposition fields (`lead_score`, `lead_status`, `qualification`, `outcome`, `conversation_end_reason`, `followup_required`); recording fields (`recording_url_encrypted`, `recording_sid`, `recording_status`, `recording_retention_until`); and campaign-sheet linkage (`sheet_url`, `sheet_row`).

**`call_events`** — `id`, `call_log_id` (FK), `call_sid`, `event_type`, `event_source`, `event_data` (longtext, presumably JSON), `created_at`. A structured event timeline per call, complementary to the summary fields on `call_logs` itself.

**`realtime_usage`** — `id`, `call_log_id` (FK), `model_name`, `voice_name`, `input_audio_tokens`, `output_audio_tokens`, `input_text_tokens`, `output_text_tokens`, `cached_input_audio_tokens`, `cached_input_text_tokens`, `user_speech_seconds`, `assistant_speech_seconds`, `estimated_cost_usd`, `usage_data` (longtext JSON snapshot), `created_at`. This is the authoritative per-call OpenAI Realtime billing record; `call_logs`'s own token/cost columns are a denormalized summary of the same data for query convenience.

**`conversations`** — `id`, `customer_id` (FK), `call_sid` (FK-like), `event_id` (unique — used for idempotent transcript persistence), `speaker`, `message`, `timestamp`, `created_at`. The raw turn-by-turn transcript log.

**`lead_qualifications`** — `id`, `call_log_id` (FK), `customer_id` (FK), `extracted_name`, `extracted_phone`, `company`, `requirement`, `budget`, `timeline`, `lead_score`, `qualification`, `confidence_score` (decimal(6,5)), timestamps. Structured extraction output from a call, distinct from the free-text `call_logs.summary`.

### Platform

**`knowledge_documents`** — `id`, `title`, `document_type`, `file_name`, `file_path`, `content` (longtext), `language`, `status`, timestamps. **No `organization_id` column** — knowledge base content is currently global, not per-tenant. This is consistent with a single-organization deployment today and should be revisited alongside [ADR-008](#) if multiple organizations with genuinely different knowledge content are ever onboarded.

**`system_settings`** — `id`, `setting_key` (unique), `setting_value` (longtext), `is_secret`, timestamps. A generic key-value settings store; `is_secret` suggests an intent to mask certain values in any admin UI that lists settings — verify this flag is actually respected wherever settings are rendered.

**`assistant_chat_messages`** — `id`, `organization_id` (FK), `user_id` (FK), `role`, `message`, `page_path`, `created_at`. Backing store for the in-app "Ask DigiDara" assistant chat surface, distinct from customer-facing call conversations.

**`provider_callback_events`** — `id`, `provider`, `event_type`, `event_key`, `call_log_id` (FK), `payload` (longtext JSON), `created_at`. The idempotency ledger: every Plivo webhook delivery is recorded here via `INSERT IGNORE` keyed on `(provider, event_type, event_key)`, so a retried webhook (Plivo redelivers on timeout) is a no-op rather than a duplicate side effect.

## Tenancy Scoping Pattern

Tables fall into two groups:

1. **Directly org-scoped:** `organizations`, `app_users`, `customers`, `campaigns`, `call_logs`, `suppression_list`, `api_credentials`, `audit_logs`, `assistant_chat_messages` — each carries its own `organization_id` column.
2. **Indirectly org-scoped via a parent FK:** `conversations`, `customer_memory`, `followup_reminders`, `lead_qualifications`, `realtime_usage`, `call_events` reach their organization only by joining through `customer_id` or `call_log_id`. This is a normal, intentional normalization choice (avoiding a duplicated `organization_id` on every child table) **provided every query that needs org-scoping actually performs that join** — this is worth an explicit code-review check once tenancy enforcement (Epic A) is underway, since a child-table query that forgets the join has no column-level safety net to catch the omission.
3. **Not org-scoped at all:** `knowledge_documents`, `system_settings`, `provider_callback_events` — global by current design; revisit only if genuine per-tenant divergence in these concerns becomes a real requirement.

## Migration Strategy

A `migrations/` directory exists in the repository for schema migration scripts. Any schema change should:

1. Be additive where possible (new nullable column, new table) to avoid a coordinated deploy-and-migrate step for a single-instance deployment.
2. Include the `organization_id` column on any new tenant-scoped table from the outset — retrofitting it later, after real multi-tenant data exists, is categorically more expensive (see [ADR-008](#)'s rationale for why the schema was built this way from the start).
3. Be paired with a rollback script or a clearly documented manual rollback procedure — no automated migration rollback tooling exists today; see [DEPLOYMENT_GUIDE.md](#).

## Repository Pattern

There is no formal repository-pattern abstraction layer (e.g., a `CustomerRepository` class) — service functions in `app/services/*.py` directly own their SQL. This is consistent with the "no ORM, explicit SQL" decision (ADR-007) and is an appropriate level of abstraction for the current codebase size. If query duplication across services becomes a measured maintenance burden, introducing a thin repository layer per aggregate (customer, call, campaign) is the natural next step — not before that burden is real, per the "no speculative abstraction" principle in [ENGINEERING_GUIDELINES.md](#).

## Indexes

Confirmed unique/primary/foreign-key indexes include `organizations.slug`, `app_users (organization_id,email)`, `customers (organization_id,email)`, `call_logs.call_sid`, `call_logs.correlation_id`, `user_sessions.refresh_token_hash`, `conversations.event_id`, `customer_memory.customer_id`, and `system_settings.setting_key`, plus standard FK indexes. If analytics queries become slow at higher volume, the first candidates for additional covering indexes are `call_logs (organization_id, campaign_id, created_at)` and `call_logs (organization_id, status, created_at)`.

## Performance Considerations

- `call_logs` is wide (over 60 columns) and is both the primary write target during a live call (frequent small updates as the call progresses) and the primary read target for analytics. At meaningfully higher call volume, consider whether hot-path call-progress writes and cold analytics reads should be split (e.g., a narrower `call_logs` plus a separate analytics-oriented denormalized table or materialized view) — not a concern at current volume.
- `realtime_usage.usage_data` and `call_events.event_data` store JSON as `longtext` rather than MySQL's native `JSON` type (unlike `audit_logs.metadata_json`, which does use `JSON`). Consider standardizing on the native `JSON` type for new JSON-blob columns, since it enables MySQL-side JSON path queries `longtext` cannot support — a minor consistency improvement, not urgent.

## Retention

`organizations.data_retention_days` and `call_logs.recording_retention_until` exist as retention-control fields. No scheduled job currently enforces either — retention today is effectively indefinite. This must be addressed before the system handles real customer voice recordings at any meaningful scale, both for storage cost and for data-protection obligations tied to `organizations.data_retention_days` actually meaning something (see [ENGINEERING_ROADMAP.md](#) Epic G, [SECURITY_GUIDE.md](#) Incident Response).
