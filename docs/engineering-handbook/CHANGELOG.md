# Changelog

This changelog tracks architecturally significant milestones, not every commit. See git history for line-level detail.

## Current Milestone — Prototype Hardening Pass (2026-08-05)

A focused engineering pass converting several known-broken or known-incomplete behaviors in the working prototype into fixed, tested functionality, plus this documentation package.

### Fixed
- **English response latency after fragmentation tuning:** call 47 confirmed semantic-VAD `medium` produced 4.813-second first, 3.051-second average, and 5.375-second maximum caller-visible response latency. English now uses automatic server VAD with a bounded 650 ms silence window; Tamil retains its separate validated semantic-VAD path.
- **Missed provider callback reconciliation:** authenticated call-log polling now checks answered Plivo calls that are at least 45 seconds old and never established a media stream. Only an authoritative terminal CDR cause can finalize the row, preventing missed Cloudflare hangup callbacks from leaving permanent `in-progress` cards while avoiding false termination of genuinely active calls.
- **Live-call turn safety, language adherence, and latency visibility:** unclear/partial speech is now explicitly excluded from `end_call` intent; English stays in English unless the customer explicitly requests Tamil; Tamil uses high semantic-VAD eagerness behind its existing validated-turn gate; response latency now includes the VAD wait from the caller's last voiced frame; and DTMF selection persists the actual language on both the customer and current call log.
- **Tamil Realtime mini rollback:** after two live mini calls showed loss of campaign purpose and an incorrect `end_call` on a greeting, the Tamil-specific configuration was restored to `gpt-realtime-2.1`. English remains on mini; Tamil transcription, voice, and turn handling are unchanged.
- **Tamil Realtime model switched to mini:** the Tamil-specific configuration now selects `gpt-realtime-2.1-mini`, matching the existing English cost-sensitive tier while preserving Tamil transcription, voice, prompt, and turn-handling behavior. The owner made this operational decision while API credits were unavailable; a controlled live Tamil quality check remains required after credits are restored.
- **Open workspace registration and workspace-aware login:** anyone can create an organization and its first administrator atomically without an operator key. The sign-in flow accepts and remembers the unique workspace ID, allowing the same email address to belong to separate organizations without ambiguous tenant selection. A real-MySQL integration test creates two temporary workspaces with one shared email, proves cross-tenant customer/campaign denial, and removes the fixtures.
- **Organization-level data isolation:** signed sessions bind the user's organization to the database-backed principal; audited customer, campaign, call, insight, chat, lead, suppression, and admin-user operations are tenant-scoped; provider callbacks derive organization from correlated records; customer emails are unique per organization; and representative cross-tenant regression coverage was added. Per-tenant credentials, tenant-specific knowledge content, production onboarding lifecycle, and RBAC remain future product work.
- **Account lockout enforcement:** `/auth/login` now atomically counts consecutive failed passwords, returns authoritative remaining-attempt/retry information, rejects locked attempts before password verification, and clears the counter/lock after a successful login. The sign-in page displays attempts remaining and a persistent backward timer. The current configurable policy is three failures for 60 seconds; five failures for 15 minutes is reserved for the later production policy.
- **Cache-unaware OpenAI estimates:** Realtime usage stored cached input counts but charged every input token at the uncached rate. Cost estimation now subtracts the cached subset and applies the correct full/mini cached rates, includes transcription usage, and version-tags the calculation. Eighteen retained local usage records were backfilled atomically.
- **Mixed-provider INR display:** OpenAI estimates and Plivo API costs were converted through one application exchange rate. Billing now presents estimated OpenAI and recorded Plivo cost separately, using independent configured INR rates and clearly labelling combined INR values as estimates.
- **English call termination:** the AI could say goodbye but the call would never hang up. Root cause: `schedule_graceful_customer_hangup()` was gated behind `if language == "tamil":`, so English calls never reached it. Fixed to fire for both languages; verified via test suite and a live call confirming Plivo's "Hangup Source: API Request."
- **Campaign automation (bulk calling):** `customer_service.upsert_customer` and `google_sheets_service.update_sheet_status` were called throughout the codebase but did not exist as functions anywhere — confirmed via direct search returning zero definitions. Implemented both, plus fixed a keyword-argument mismatch in `/calls/run-sheet` (`customer_phone` vs. the expected `phone_number`) that would have crashed call placement even after the missing functions were added.
- **Do-not-call/suppression enforcement bundled into the same fix:** added `telephony_service.is_suppressed()`, wired into the single call-placement choke point (`start_outbound_call`) and both queue-advancement sites (`trigger_next_queued_call`, `/calls/run-sheet`'s candidate selection) so a suppressed lead is skipped and marked, never dialed, and never silently stalls the rest of the queue.
- **Missing transcription-cost tracking:** Realtime cost calculations omitted the separate ASR transcription model's billing entirely. Added `_transcription_token_rates()` and wired its cost into both the live cost snapshot and the final `realtime_usage` insert.
- **Non-model-aware cost formula:** cost calculations previously used a flat rate regardless of which Realtime model tier served the call; now keyed on the actual model recorded per call.
- **Sheet header recognition gap:** a real customer sheet's "Phone no" header was not recognized by `normalize_headers()`, which would have silently skipped every row in a bulk campaign. Added the missing alias plus several Mobile/Contact variants.
- **Tamil prompt over-broad English-switch instruction:** the Tamil conversation policy instructed the model to switch fully to English whenever the customer "spoke English" — this fired incorrectly when the customer merely used an English loanword for a course term (e.g., "hybrid mode"), producing one full English-language turn mid-Tamil-call. Tightened the instruction to require a full English sentence, not just an English word, before switching.

### Added
- **AI-judged call termination via tool calling:** replaced reliance on keyword/regex pattern matching for the terminal end-of-call decision with an `end_call` function tool the model invokes based on its own judgment of customer intent, in either language. Regex-based classification remains for structured CRM disposition tagging, not as the terminal gate.
- **DTMF language selection menu:** every outbound call now opens with a "Press 1 for English, Press 2 for Tamil" menu before the AI conversation begins, giving the customer explicit control over call language — previously, language was implicitly (and, on inspection, incorrectly) assumed from campaign selection or sheet metadata, with no code path actually reading a campaign's intended language (the `campaigns` table has no `language` column at all).
- **Pre-rendered DTMF prompt audio:** the language menu's audio is rendered once via OpenAI's TTS REST endpoint and played back via Plivo's `<Play>`, after a live test revealed Plivo's native `<Speak>` cannot render Tamil speech at all.
- **`tests/test_campaign_automation.py`:** 9 new tests covering `upsert_customer`, `update_sheet_status`, and `is_suppressed`, establishing this codebase's first `MagicMock`-based database-mocking test pattern.
- **This documentation package** (20 documents plus a master index), covering architecture, security, database, voice platform, AI platform, deployment, testing, roadmap, and AI-coding-assistant context.

### Investigated and Found Not to Be a Bug
- **Telephony cost estimate accuracy:** a suspected discrepancy between the app's stored telephony cost and Plivo's real billing was investigated by comparing `estimated_telephony_cost_usd` against live Plivo CDR data (`get_call()`) across every completed call. The stored values matched exactly in every case. Reported as a non-issue (a currency-display artifact, not a cost-tracking bug) rather than patched.

### Identified, Not Yet Fixed (tracked in `TECHNICAL_DEBT.md` / `ENGINEERING_ROADMAP.md`)
- Tenant product completion: open registration still lacks email verification, anti-abuse controls, and payment entitlements; provider credentials and knowledge content remain global, and authorization remains admin-only.
- No per-IP login rate limiting or MFA; per-account lockout is implemented.
- Development ingress (Cloudflare Quick Tunnels) is ephemeral and unsuitable for any non-local environment.
- `language_switch` intent detection only recognizes the ASCII substring `"english"`, missing Tamil-script requests to switch languages.
- One observed case of `conversation_end_reason` left `NULL` on a completed Tamil call despite code appearing correct — flagged for follow-up investigation, not yet root-caused.

## Prior Milestone — Bilingual Realtime Architecture

Documented in `IMPLEMENTATION_REPORT.md`: the shared English/Tamil realtime counsellor architecture, including the restoration of English's automatic-VAD consultative sales flow after a bilingual refactor had regressed it onto Tamil's manual turn-planner, and the introduction of `conversation_policy_service.py` as the shared policy layer for both languages.

## Future Milestones

- **M1 — Reproducible & Verified:** pinned dependencies, CI, stable non-local ingress. (`ENGINEERING_ROADMAP.md` Epics A/B/C)
- **M2 — Tenancy-Safe:** organization context enforced everywhere, account lockout enforced, per-endpoint authorization audited. (Epic A)
- **M3 — Proven at Volume:** a real bulk campaign run against a full-size lead sheet with provisioned credentials. (Epic D)
- **M4 — Operationally Mature:** containerized deployment, documented rollback, full audit-log coverage, enforced data retention. (Epic G)
- **M5 — Platform:** per-tenant credentials and RBAC live, a second telephony or AI provider integrated behind existing abstractions, additional languages onboarded. (`FUTURE_VISION.md` Stage 5)
# 2026-08-06 - Cost-aware reporting and call guardrails

- Applied cached-input token rates to OpenAI Realtime cost estimates and separated estimated OpenAI INR from recorded Plivo INR presentation.
- Added a configurable provider-enforced maximum duration shared by individual and bulk calls.
- Added post-call cost, cost-per-minute, turn-rate, interruption, and false-turn alert signals to authenticated call-log APIs.
- Added dashboard alert counts, health badges, alert-only filtering, and call-level operational metrics.
