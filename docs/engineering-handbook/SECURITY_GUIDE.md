# DigiDARA — Security Guide

## Authentication

- Credentials are verified against `app_users.password_hash`, hashed with PBKDF2-HMAC-SHA256 using a unique random salt and 310,000 iterations (`app/services/auth_service.py`: `hash_password`/`verify_password`). Plaintext passwords are never stored or logged.
- Sessions use an application-issued HMAC-SHA256 bearer token: `issue_token(user)` on successful login or admin bootstrap and `decode_token(token)` for signature and expiry validation. The `current_admin` FastAPI dependency then reloads the user and requires an active administrator account.
- Every private HTTP route is covered by `current_admin`. The deliberately public HTTP surface is limited to login/onboarding status, open workspace registration, protected first-admin bootstrap, static language-prompt audio, legacy telephony callbacks, and the signed Plivo callback path. `tests/test_auth_coverage.py` fails if a newly added application HTTP route is neither authenticated nor explicitly classified as public.
- `/auth/workspaces` is the normal open path for creating a new organization and its first administrator. The older `/auth/bootstrap-admin` setup/recovery path remains gated by an `ADMIN_BOOTSTRAP_KEY` environment secret of at least 12 characters and returns `409` once any password-backed administrator exists. Do not reuse that operator secret as a customer registration credential.
- Account lockout is enforced through `authenticate_user()`: failed passwords atomically increment `failed_login_attempts`; the current policy locks an account after three consecutive failures for 60 seconds; locked requests are rejected before password verification; and a successful login clears both the counter and `locked_until`. `AUTH_MAX_FAILED_LOGIN_ATTEMPTS` and `AUTH_ACCOUNT_LOCKOUT_SECONDS` configure the bounded policy. The login API returns authoritative attempts remaining or retry seconds, and the sign-in page displays a persistent countdown. The planned production policy is five attempts and 15 minutes after operational testing.
- `mfa_enabled` exists as a schema column with no MFA flow implemented yet. Do not present this field as "MFA is supported" in any customer-facing material until an actual second factor is implemented.

## Authorization

- Authorization is currently binary: all private HTTP routes require `current_admin`, which requires `role_code == "admin"`, an active user, and an active organization. The signed token organization must match the database-backed user organization. There is still no non-admin role with a defined permission set.
- Admin creation inherits the authenticated admin's organization. The legacy first-admin bootstrap selects the configured active organization instead of assuming tenant `1`; new organizations use the open workspace registration flow below.
- `POST /auth/workspaces` intentionally allows registration without an operator secret. The organization, first administrator, and audit event are committed atomically. The workspace ID is supplied during login and scopes account lookup before password verification. The legacy `/auth/bootstrap-admin` route remains protected by `ADMIN_BOOTSTRAP_KEY` because it is a separate recovery/setup mechanism.
- Open registration is approved for the current local phase, but must not be exposed as commercial internet signup without email verification, per-IP/per-identity rate limiting or CAPTCHA, account recovery/suspension, and server-enforced payment entitlements. Until payment integration is implemented, a newly registered administrator has the same product permissions as existing administrators.
- When RBAC is built out (Epic A), design permissions around the concrete roles this business actually has (counsellor, campaign manager, org admin, platform admin) rather than a generic permission-string system with no real consumers yet — consistent with the "no speculative abstraction" principle in [ENGINEERING_GUIDELINES.md](#).

## Tenant Isolation

- Schema-level isolation exists for the operational core, and customer email uniqueness is composite on `(organization_id, email)` rather than global.
- Application-level isolation derives organization context from the authenticated principal for private routes and from signed provider-correlated customer/campaign records for the Plivo/OpenAI call path. The audited customer, campaign, call, insight, chat, lead, suppression, and admin-user queries are scoped by organization. Regression tests cover token binding, direct service queries, cross-tenant call-detail denial, analytics, and indirect chat/lead/memory paths.
- This does not yet make the platform complete multi-tenant SaaS: Plivo/OpenAI/CRM credentials and live-call organization knowledge are tenant-scoped, but Google Sheets credentials remain environment-level, the restricted legacy knowledge surface is not tenant-aware, open registration lacks abuse controls and payment entitlements, and RBAC remains admin-only.

## Secrets Management

- `.env` holds live secrets (OpenAI API key, Plivo auth ID/token, DB password, JWT secret) and is `.gitignore`d; `.env.example` documents every variable without real values.
- `credentials.json` (Google service-account key) is resolved at runtime by `find_credentials_file()` — env var override first, then a small set of candidate paths — and is `.gitignore`d. It must never be committed, and must be provisioned per-environment (see [ENGINEERING_ROADMAP.md](#) Epic D) rather than shared from one developer's machine.
- `JWT_SECRET` must be a long, random value — the `.env.example` placeholder (`replace_with_a_long_random_secret`) is exactly that, a placeholder, and was confirmed during this engineering pass to still be present verbatim in a live `.env` at one point; any environment still using a placeholder secret must rotate it before being treated as anything other than throwaway/local.
- Plivo webhook validation depends on `PLIVO_AUTH_TOKEN` (used as the HMAC key material, alongside a dedicated `PLIVO_STREAM_TOKEN_SECRET` fallback chain in `plivo_stream.py`'s `_stream_secret()`) — treat both as tier-one secrets.
- `api_credentials.credential_ciphertext` stores encrypted per-tenant Plivo and OpenAI credentials, while `crm_connections` stores encrypted tenant CRM webhook configuration. Environment values remain controlled fallbacks for local/single-tenant operation. Google Sheets service-account credentials are still environment-level and must be provisioned as deployment secrets.

## OWASP-Relevant Controls Already in Place

- **Injection:** All SQL is parameterized via PyMySQL placeholders; no string-formatted SQL was found anywhere in the reviewed service/API code.
- **Broken authentication:** Addressed for PBKDF2-HMAC-SHA256 password storage, signed sessions, and per-account lockout; per-IP throttling and MFA remain open.
- **Sensitive data exposure:** Recordings are referenced via `recording_url_encrypted` (an encrypted-at-rest column) rather than a raw public URL; do not regress this by ever storing a plaintext recording URL in a new column.
- **Untrusted content boundary:** Campaign `ai_prompt` text is explicitly delimited with an `<untrusted_campaign_content>` wrapper in the conversation-policy builders, with an instruction to the model to treat it as goals/facts and ignore any instruction inside it that conflicts with the permanent policy — this is the system's mitigation for prompt-injection risk from operator-authored campaign content, and any new source of model-context content (e.g., knowledge-base documents, future CRM notes) should be evaluated for whether it needs the same boundary treatment.
- **Signed webhooks:** Every Plivo webhook is validated against Plivo's V3 HMAC signature (`_signed_form` in `app/api/plivo.py`) before its payload is trusted, with a `PLIVO_VALIDATE_SIGNATURES` escape hatch defaulting to `true` and additionally forced on outside of `development` environment mode — do not disable this in any non-local environment.

## OWASP-Relevant Gaps to Close

- **Broken access control:** the audited operational data boundary is organization-scoped; non-admin RBAC, commercial tenant lifecycle controls, environment-level Google credentials, and the restricted legacy knowledge surface remain the principal access-model gaps.
- **Security logging & monitoring failures:** `audit_logs` exists and is used for admin-account creation only today; calling, customer-data export, credential rotation, and suppression-list changes are not yet audit-logged. Expand coverage per [ENGINEERING_ROADMAP.md](#) Epic G.
- **Rate limiting:** no per-IP rate limiting exists on `/auth/login`, `/auth/bootstrap-admin`, or any other endpoint. Per-account lockout now limits repeated password guessing against known accounts, but IP-based throttling remains recommended before internet-facing deployment to reduce distributed attempts and login-endpoint load.

## Rate Limiting

Not currently implemented anywhere in the reviewed API surface. Prioritize, in order: `/auth/login` (brute force), `/auth/bootstrap-admin` (guards first-admin creation), any future public-facing lead-capture endpoint. A per-IP and per-account limiter is sufficient for current scale; do not over-engineer a distributed rate-limiting system before there is more than one application instance to coordinate across.

## Input Validation

- Pydantic v2 schemas validate shape and basic constraints (e.g., `AdminInput`'s email regex and password length bounds) at the API boundary for every route that declares a schema.
- Phone numbers are normalized and digit-stripped before use (`telephony_service.normalize_phone`, `customer_service.upsert_customer`'s `re.sub(r"\D", "", phone)`), which doubles as a lightweight injection defense for a field that flows into both SQL parameters and an external API call.
- Sheet-sourced data (name, phone, language, course fields) is treated as untrusted input: it is normalized, length-implicitly-bounded by the customer schema, and never interpolated directly into SQL or into a live prompt without going through the same field-population path as manually-entered CRM data.

## Encryption

- Passwords: PBKDF2-HMAC-SHA256, one-way, with a unique random salt and 310,000 iterations.
- Call recordings: referenced via an encrypted column (`recording_url_encrypted`); the encryption key/mechanism for this column should be documented explicitly wherever it is implemented and rotated on a defined schedule — confirm this is using `DATA_ENCRYPTION_KEY` (present in `.env.example`) consistently.
- Third-party credentials: designed to be stored as ciphertext in `api_credentials.credential_ciphertext`, with `key_version` supporting key rotation — this table's encryption implementation should be finished and load-bearing before any per-tenant credential is migrated into it.
- Transport: all provider webhooks and the Realtime WebSocket connection use TLS/WSS in any non-local environment; local development's use of an HTTP/WS Cloudflare Quick Tunnel endpoint is a development-only exception, not a production pattern.

## Audit Logging

- `audit_logs` (organization-scoped, actor-attributed, with `action`, `resource_type`, `resource_id`, `result`, and a `metadata_json` field) is the correct mechanism and schema for this; today it is only written to on admin-user creation.
- Priority actions to add audit coverage for, in order: authentication events (login success/failure, lockout trigger), suppression-list changes (a compliance-sensitive action), customer data export/deletion, credential rotation, and campaign creation/modification (since campaign `ai_prompt` content directly drives what the AI says to customers).

## Incident Response

No formal incident-response process exists in the repository today. At minimum, define and document:

1. **Webhook/signature-validation failure spike:** what it means (likely a misconfigured `PLIVO_AUTH_TOKEN`/`PLIVO_STREAM_TOKEN_SECRET`, or an actual spoofing attempt) and who is paged.
2. **Suppression-list bypass suspicion:** given the compliance sensitivity of do-not-call enforcement, define a process to audit recent calls against `suppression_list`/`customers.do_not_call` if a bypass is ever suspected, using `is_suppressed`'s own logic as the verification query.
3. **Credential leak (OpenAI/Plivo/Google/JWT secret):** rotation steps for each secret type, and what depends on each (e.g., rotating `JWT_SECRET` invalidates all existing sessions — `user_sessions.refresh_token_hash` records exist to support this).
4. **Data-subject deletion/export request:** the schema supports soft-deletion (`customers.deleted_at`) but no documented process exists yet for handling an actual request; this should be defined before the system holds a meaningful volume of real customer data.
