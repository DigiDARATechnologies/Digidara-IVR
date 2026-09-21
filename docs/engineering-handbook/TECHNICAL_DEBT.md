# DigiDARA — Technical Debt

This document lists known debt honestly, including debt discovered but not yet resolved. Nothing here should be read as an emergency — most of it is appropriate debt for a system at this stage — but all of it should be visible rather than tribal knowledge.

## Current Debt

The previously tracked P0 gaps for a pinned backend manifest and continuous integration were closed on 2026-08-05. Account lockout and the audited organization-scoped application data boundary were closed on 2026-08-06. Direct backend dependencies are pinned in `app/requirements.txt`; `.github/workflows/ci.yml` installs them and runs the backend suite plus the locked frontend build on every push and pull request.

### Signup hardening, Google credential ownership, and payment entitlements are incomplete
Authenticated tenant data, live-call organization knowledge, and encrypted Plivo/OpenAI/CRM credentials are organization-scoped. Open registration can create a workspace and first admin atomically, and login selects by workspace ID, including when the same email exists in multiple organizations. Google Sheets still uses an environment-level service-account credential, the retained legacy Chroma knowledge surface is restricted rather than tenant-aware, and registration has no email verification, abuse prevention, suspension/recovery lifecycle, or payment gate. **Risk:** a newly registered administrator currently receives full application access, including billable calling operations, and independent customers cannot yet own isolated Google credentials or delegated roles. **Cleanup:** add server-enforced subscription entitlements before commercial access, then complete signup hardening, RBAC, and tenant-owned Google integration provisioning before presenting the platform as finished multi-tenant SaaS. **Priority: P1 before public or independent commercial onboarding.**

### Frontend dependency security advisories require planned major upgrades
The locked frontend install currently reports five npm advisories (three moderate and two high). The remaining affected dependency chains include Vite/esbuild and React Router; npm's available remediations require major-version upgrades, so `npm audit fix --force` was deliberately not applied during CI hardening. **Risk:** the Vite findings primarily affect the local development server, while the React Router advisory class can affect client-side navigation. **Cleanup:** schedule tested Vite 8 and React Router 7 upgrades, then rerun the production build and application navigation/login regression checklist. **Priority: P1 before exposing a shared development server or commercial frontend.**

### Ephemeral development ingress (Cloudflare Quick Tunnels)
The public webhook URL Plivo calls back to is a `trycloudflare.com` hostname that changes every time the tunnel process restarts. **Risk:** already caused one live call-creation failure (`ValidationError`) traced to a stale hostname in `.env`. Not viable for any non-local environment. **Cleanup:** provision a stable ingress before any non-local deployment. **Priority: P0 for any non-local environment; not urgent for pure local development.**

### `google_sheets_service.update_sheet_feedback` has no fallback and fails loudly without `credentials.json`
By design, this is the *correct* failure mode (loud, not silent), but it means bulk-campaign status write-back is entirely dependent on a single developer's local credential file today, with no per-environment provisioning process. **Risk:** cannot fully validate or run bulk-campaign auto-progression outside whichever machine happens to have `credentials.json`. **Cleanup:** provision per-environment service-account credentials. See [ENGINEERING_ROADMAP.md](#) Epic D. **Priority: P0 before any real bulk-campaign run.**

### `language_switch` intent detection is ASCII-substring-only
`openai_realtime.py`'s `if latest_intent == "language_switch": response_language = "english" if "english" in text.casefold() else "tamil"` only ever detects the literal ASCII word "english" in the (possibly Tamil-script) transcript text. A Tamil-script request to switch to English (e.g., using the Tamil word for "English") would fall through to the `else` branch and incorrectly stay/default to Tamil. **Risk:** low-frequency but real misclassification of an explicit customer request. **Cleanup:** detect Tamil-script language-name words alongside the ASCII check. **Priority: P2** — this is a narrow, well-understood, low-blast-radius gap, not urgent relative to the P0 items above.

### Legacy/exploratory code paths retained alongside the active production path
`app/services/twilio_service.py`, `app/api/conversation_relay.py`, `app/livekit_agent/`, and the alternative TTS integrations (`elevenlabs_service.py`, `gemini_service.py`, `groq_service.py`, `sarvam_service.py`) are not part of the confirmed active production call flow (Plivo + OpenAI Realtime), per the direct trace in `IMPLEMENTATION_REPORT.md`. **Risk:** a new engineer could reasonably mistake one of these for the active path and spend time modifying dead code, or worse, both an active and a legacy path could be modified inconsistently if a change is made in the wrong place. **Cleanup:** either explicitly mark these modules as archived/exploratory in-code (a module-level docstring stating "not the active production path" — several already have adjacent comments to this effect, but not all), or, if genuinely unused, remove them in a dedicated cleanup pass with git history preserving them for reference. **Priority: P2** — no functional risk today, but a documentation/clarity risk that compounds as the codebase grows.

### Raw SQL duplication across similar CRUD functions
`get_customer_by_id`, `get_customer_by_email`, and similar functions each hand-write the same column list. **Risk:** a schema change to `customers` (e.g., adding a column that should be part of the standard select set) requires updating multiple call sites by hand, with a real chance of missing one. **Cleanup:** a shared column-list constant or a thin per-aggregate repository helper, once this duplication is measured as an actual maintenance cost — not before. **Priority: P2.**

### `estimated_twilio_cost_usd` column name is a legacy artifact
`call_logs.estimated_twilio_cost_usd` predates the Plivo migration and is a naming artifact from when Twilio was the telephony provider; the actually-used, live-reconciled field is `estimated_telephony_cost_usd`. **Risk:** low — but a new engineer reading the schema cold could reasonably wonder which field is authoritative. **Cleanup:** document (as done here) or, in a dedicated migration, rename/deprecate the legacy column explicitly. **Priority: P2.**

### JSON-as-longtext instead of native `JSON` type
`realtime_usage.usage_data` and `call_events.event_data` are `longtext` rather than MySQL's native `JSON` type (unlike `audit_logs.metadata_json`, which does use `JSON`). **Risk:** none functionally; forecloses MySQL-side JSON path querying for these columns specifically. **Cleanup:** standardize on native `JSON` for new JSON-blob columns going forward; migrating existing columns is optional and low-priority. **Priority: P2.**

### `knowledge_documents` has no `organization_id`
Knowledge-base content is global today, not per-tenant. **Risk:** a second organization cannot have independently governed approved content even though its operational data is isolated. **Cleanup:** add tenant ownership and scoped retrieval before independent tenant onboarding. **Priority: P1 before a second independent commercial tenant.**

## Future Debt (Watch Items — Not Yet Real Problems)

- **`call_logs` table width:** over 60 columns, serving both hot-path per-call writes and cold analytics reads. Not a problem at current volume; worth revisiting (a possible read/write split) only if analytics queries measurably slow down as call volume grows.
- **No repository/abstraction layer over Google Sheets or CDR billing reconciliation:** appropriate today with exactly one concrete implementation of each; would become debt only if a second sheet-like data source or a second billing-reconciliation provider is actually introduced without first extracting an interface, mirroring the telephony abstraction's pattern.
- **No automated conversation-quality evaluation:** current quality assurance is manual live-call review plus cost/latency telemetry. As conversation volume grows, the absence of automated evaluation will increasingly mean quality regressions are found by customers or campaign owners before they're found internally.

## Legacy Code

The Twilio-era pipeline (`twilio_service.py`, `conversation_relay.py`) and the LiveKit agent (`app/livekit_agent/`) represent prior architectural iterations retained in the repository. Neither should be extended or relied upon for new work without first confirming — via the same kind of direct production-path trace performed in `IMPLEMENTATION_REPORT.md` — that it is genuinely still inactive. Treat any request to "add a feature to the voice call flow" as targeting `app/api/openai_realtime.py` and the Plivo integration unless a specific reason is given to believe otherwise.

## Risk Summary (Ranked)

1. Tenant provisioning, per-tenant credentials, and tenant knowledge ownership (P1 before a second commercial tenant) — the application data boundary is enforced, but the surrounding SaaS onboarding model is incomplete.
2. Login rate limiting (P1) — account lockout is enforced, but per-IP throttling remains desirable before internet-facing deployment.
3. Bulk-campaign credential provisioning (P0 before real-volume use) — blocks proving campaign automation at realistic scale.
4. Frontend dependency advisories (P1) — require tested Vite and React Router major upgrades before broader exposure.
5. Ephemeral dev ingress (P0 for any non-local use, intentionally deferred while work remains local) — blocks staging/production only.
6. Remaining P2 items — real and worth tracking, but not blocking the immediate local hardening sequence.
