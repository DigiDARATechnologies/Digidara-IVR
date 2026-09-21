# DigiDARA — Architecture Decision Record (ADR)

Each entry records a single architectural decision: what was decided, why, what it costs, what else was considered, and what would make us revisit it. Entries are numbered sequentially and never renumbered; a superseded decision is marked as such rather than deleted.

---

### ADR-001: OpenAI Realtime API as the sole conversational engine (speech-to-speech, not pipeline)

**Status:** Accepted, implemented.

**Decision:** Live calls are handled by a direct, bidirectional WebSocket bridge between Plivo's audio stream and OpenAI's Realtime API. There is no separate ASR → text LLM → TTS pipeline for the conversation turn itself.

**Reason:** A pipelined architecture (transcribe, then reason, then synthesize) adds latency at every stage and loses prosody/paralinguistic information between stages. Realtime's speech-to-speech model collapses this into one round trip, which matters directly for a phone conversation where every extra 500ms of silence reads as the AI being unresponsive.

**Tradeoffs:** Less controllability — you cannot easily inspect or veto "what the model is about to say" before it is spoken, because generation and speech happen together. Debugging requires reasoning about a live bidirectional stream rather than inspecting discrete request/response pairs. Cost accounting is more complex (see ADR-006) because Realtime bills audio and text tokens separately from a parallel transcription model used for logging.

**Alternative considered:** Twilio + a classic STT/LLM/TTS pipeline. This path still exists in the repository (`app/services/twilio_service.py`, `app/api/conversation_relay.py`) but is not the active production path — confirmed by direct trace of the live call flow (`IMPLEMENTATION_REPORT.md`, section 4).

**Future review trigger:** If OpenAI Realtime pricing or availability changes materially, or if a second Realtime-capable provider becomes viable, revisit whether the bridge layer (`app/api/openai_realtime.py`) should be abstracted behind a provider interface the way telephony already is (see ADR-003).

---

### ADR-002: Two different turn-taking architectures for English vs. Tamil, inside one session type

**Status:** Accepted, implemented.

**Decision:** English uses OpenAI's automatic server voice-activity detection (`create_response: true`, `interrupt_response: true`) with a bounded 650 ms silence window. Tamil uses semantic VAD plus a manual, validated-latest-turn planner (`create_response: false`) with RMS-based turn validation and an explicit `trigger_latest_response` call.

**Reason:** English semantic VAD at high eagerness fragmented a real five-minute call, while medium eagerness produced 4.813-second first and 5.375-second maximum caller-visible delay on a later test. Server VAD gives English a predictable silence bound without the semantic classifier's variable timeout. Automatic VAD did not perform acceptably for Tamil callers in practice, so Tamil retains the conservative mechanism: buffer the turn, validate it against duration/peak-RMS/voiced-frame thresholds, discard the turn if it fails validation, and only submit the newest validated turn.

**Tradeoffs:** Two conversational code paths to maintain instead of one; a change to shared behavior (e.g., the `end_call` tool, in ADR-004) must be verified against both flows independently, as happened when the English hangup path was found to be dead code gated behind `if language == "tamil":` while the equivalent Tamil path worked.

**Alternative considered:** Keep English semantic VAD at `high` (faster but fragmented) or `medium`/`auto` (less fragmentation but unacceptable variable wait). For Tamil, tuning `OPENAI_VAD_EAGERNESS_TAMIL` alone remains insufficient given the observed false-turn rate, so its manual planner remains.

**Future review trigger:** If OpenAI's semantic VAD is retrained or a language-aware VAD mode becomes available, re-evaluate whether Tamil can move to the simpler automatic path.

---

### ADR-003: Provider-neutral telephony abstraction (`app/services/telephony/`)

**Status:** Accepted, implemented.

**Decision:** Call orchestration code (`telephony_service.py`) depends on a `get_telephony_provider()` interface, not on the Plivo SDK directly. `PlivoProvider` is the only current implementation.

**Reason:** Telephony providers are commodity infrastructure with meaningfully different pricing, reliability, and regional coverage; locking orchestration logic to one SDK's call shape would make a future provider migration or multi-provider failover strategy far more expensive than the upfront cost of one abstraction layer.

**Tradeoffs:** A small amount of indirection for a system that, today, only has one implementation — the interface's shape is partly speculative until a second provider is actually integrated.

**Alternative considered:** Call the Plivo SDK directly from `telephony_service.py`. Rejected because the CDR-billing reconciliation, V3 signature validation, and status-mapping logic (`app/services/telephony/status.py`) are exactly the kind of provider-specific detail that benefits from being isolated behind a stable interface even with a single implementation today.

**Future review trigger:** When a second telephony provider is integrated, revisit whether the interface's method signatures (`create_call`, `get_call`, `terminate_call`, `validate_callback`) generalize cleanly or need to change.

---

### ADR-004: Model-judged call termination via an `end_call` tool, not keyword matching

**Status:** Accepted, implemented. Supersedes an earlier keyword-only approach for the terminal hangup decision.

**Decision:** The Realtime session is given an `end_call` function/tool with instructions to invoke it silently, mid-turn, the moment the model judges — in any wording, tone, or language — that the customer wants the call to stop. The tool call is what ultimately triggers `schedule_graceful_customer_hangup()`. Regex/keyword-based intent classification (`conversation_end.py`, `classify_intent`) remains in the codebase as a structured signal for analytics and CRM disposition tagging (do-not-call flag, lead status), and as defense-in-depth, but is not the sole gate on ending the call.

**Reason:** Keyword and regex patterns for "the customer wants to end the call" were repeatedly found to miss real phrasings during live Tamil-language testing — new patterns were added twice to cover observed gaps (a negative-question form like "won't you cut the call," and several Tamil phrasings), and it became clear this would never be exhaustive: natural language has too many ways to express the same intent for a pattern list to keep up. The explicit user feedback that prompted this change was direct: pattern-matching "will never work for all times" — the model itself needs to make this judgment.

**Tradeoffs:** Tool-call reliability depends on the model correctly following the instruction every time, across two languages and arbitrarily many phrasings; unlike a regex, its failure mode is harder to unit-test exhaustively (mitigated by keeping the regex layer for structured, testable disposition tagging).

**Alternative considered:** Keep expanding the regex/keyword pattern list indefinitely. Rejected as fundamentally unscalable given repeated live evidence of missed phrasings.

**Future review trigger:** If tool-call reliability issues are observed in production (e.g., customers reporting the AI kept talking after clearly asking to end the call), add telemetry specifically on tool-call latency/failure rate rather than reverting to keyword-only detection.

---

### ADR-005: DTMF language selection at call start, with a pre-rendered audio prompt instead of provider TTS

**Status:** Accepted, implemented.

**Decision:** Every outbound call now opens with a Plivo `<GetDigits>` menu ("Press 1 for English, Press 2 for Tamil") before the AI stream starts. The menu audio is a clip pre-rendered once via OpenAI's TTS REST endpoint and played back with `<Play>`, not spoken live via Plivo's native `<Speak>` verb. If no valid digit arrives within the timeout, Plivo falls through to the same Record/Stream verbs that would otherwise start the call immediately, using whatever language the customer record already has (defaulting to English) — so the call never stalls on an unanswered prompt.

**Reason:** Prior to this decision, the language spoken on a call was decided by campaign selection or a sheet's `Language` column, which — on inspection — turned out to be **completely disconnected** from the campaign the operator picked in the UI: the `campaigns` table has no `language` column at all, so a campaign named "... - Tamil" was a human-readable label with no code path reading it. Letting the customer choose their own language at call start removes this disconnect entirely and gives the customer explicit agency over the interaction, rather than relying on operator-side metadata that could easily be wrong or absent.

The first implementation used Plivo's native `<Speak>` for the bilingual prompt and was found, on a live test call, to produce audible English followed by dead silence where the Tamil half of the prompt should have played — consistent with Plivo's TTS engine having no Tamil voice. This is also consistent with a pre-existing convention already in the codebase (`app/api/plivo.py`'s prior comment, "No provider `<Speak>`: OpenAI Realtime owns the single greeting and voice") that had, until this feature, kept Plivo's own TTS out of the call flow entirely.

**Tradeoffs:** Adds a fixed few seconds of menu/wait time to every call before the AI conversation begins. The pre-rendered clip must be regenerated if its wording ever changes (it is cached to disk and only (re)rendered when missing).

**Alternative considered:** Rely on Plivo's `<Speak>` with per-language `voice`/`language` attributes. Rejected after live evidence that Plivo cannot render Tamil speech at all, matching the codebase's existing avoidance of provider-native TTS.

**Future review trigger:** If the menu wording changes, or if a customer's chosen language should also override a previously-set sheet/campaign default in additional places beyond `customers.language`, revisit.

---

### ADR-006: Model-aware, transcription-inclusive Realtime cost accounting

**Status:** Accepted, implemented.

**Decision:** Live and persisted cost calculations (`app/api/openai_realtime.py`) use per-model token rate tables (`_realtime_token_rates`, `_transcription_token_rates`) rather than flat environment-variable rates, and include the separate ASR transcription model's audio-input and text-output token cost, which was previously omitted entirely from the cost formula.

**Reason:** An analytics-dashboard discrepancy was traced to two real, distinct causes on direct inspection of `realtime_usage` and `call_logs` cost fields against live OpenAI usage and Plivo billing data: (1) the transcription model (`gpt-4o-transcribe`/`gpt-4o-mini-transcribe`) runs and bills separately from the Realtime session's own audio/text tokens, and was not being tracked or charged at all; (2) the cost formula used one flat rate regardless of which Realtime model tier (`gpt-realtime-2.1` vs. its mini variant) actually served the call.

A third suspected discrepancy — that telephony cost was being overestimated relative to Plivo's real billing — was investigated by calling Plivo's CDR `get_call()` API live against every completed call in the database and comparing it to the stored `estimated_telephony_cost_usd`. The stored value matched the live provider billing exactly in every case. That "bug" was reported as a non-issue rather than patched, because it was not actually a bug — the discrepancy the user observed was a currency-display artifact, not a cost-tracking one.

**Tradeoffs:** Two additional configurable rate env vars (`OPENAI_TRANSCRIBE_AUDIO_INPUT_USD_PER_M`, `OPENAI_TRANSCRIBE_TEXT_OUTPUT_USD_PER_M`) that must be kept current as OpenAI's pricing changes, on top of the existing Realtime rate env vars.

**Alternative considered:** Continue using a single flat rate and accept the inaccuracy. Rejected because unit economics (cost per call, per campaign, per organization) are a core input to the product's commercial viability and must be trustworthy.

**Future review trigger:** Any OpenAI pricing change for Realtime or transcription models; any new Realtime model tier added to campaign configuration.

---

### ADR-007: Raw parameterized SQL via PyMySQL, no ORM, in the live request path

**Status:** Accepted (pre-existing), retained.

**Decision:** All database access in `app/services/*.py` and `app/api/*.py` is hand-written, parameterized SQL against `PyMySQL` dict-cursor connections. `app/models/*.py` contains lightweight column declarations used as schema documentation/reference, not an active ORM session layer.

**Reason:** For a backend of this size and a small engineering team, raw SQL keeps query behavior fully explicit and avoids an additional abstraction layer's learning curve, migration tooling, and N+1-query footguns. It also makes it straightforward to reason about exactly what is sent to the database, which mattered directly when diagnosing the campaign-automation bug (confirming, via direct `grep`, that `upsert_customer` and `update_sheet_status` simply did not exist as functions anywhere, rather than existing but misbehaving inside an ORM abstraction).

**Tradeoffs:** No automatic migration generation (see ADR-008), more manual discipline required to keep SQL parameterized and injection-safe, and more repetition across similar CRUD functions (`get_customer_by_id`, `get_customer_by_email`, etc. each hand-write their column list).

**Alternative considered:** Adopt SQLAlchemy's ORM layer fully, using the existing `app/models/` declarations as real mapped classes. Not pursued to date; remains a legitimate option if the team grows or query complexity increases materially — see [TECHNICAL_DEBT.md](#).

**Future review trigger:** If query duplication or injection-risk code review burden becomes a measured problem, or if the engineering team grows beyond what code-review-per-query can sustain.

---

### ADR-008: Schema-first multi-tenancy, application-enforcement pending

**Status:** Partially implemented — schema accepted and in place; application-layer enforcement not yet complete. This is the single most consequential open item in the codebase today.

**Decision:** Every core table (`customers`, `campaigns`, `call_logs`, `suppression_list`, `app_users`, `api_credentials`, `audit_logs`) carries an `organization_id` column, and a dedicated `organizations` table exists with plan/quota fields (`plan_code`, `monthly_call_limit`, `data_retention_days`). This is a real, deliberate schema decision toward multi-tenant SaaS operation, not an accident of table design.

**Reason:** Building the tenancy boundary into the schema from the start avoids the far more expensive path of retrofitting a `organization_id` column onto a live, populated multi-tenant dataset later, including backfilling historical rows and auditing every existing query for the missing filter.

**Subsequent implementation (2026-08-06):** Tokens now carry an organization claim that must match the active user's database organization; active customer, campaign, call, insight, chat, lead, suppression, and admin-user paths are organization-scoped; the active provider callback path derives tenant context through the correlated campaign/customer; and customer email uniqueness is tenant-composite. The remaining tradeoff is product-level tenancy around provisioning, shared provider credentials, global knowledge content, and admin-only authorization—not an unscoped operational-data query model.

**Alternative considered:** None seriously — a schema retrofit for multi-tenancy after real customer data exists is categorically worse than this partial-completion state, which is why the schema-first approach was kept even though enforcement lagged.

**Future review trigger:** Before onboarding a second real organization/tenant, or before any external customer's data coexists with another's in the same database, this gap must close. See [SECURITY_GUIDE.md](#) and [IMPLEMENTATION_CHECKLIST.md](#) for the specific remediation checklist.

---

### ADR-009: Campaign automation — DNC/suppression enforcement bundled at the call-placement choke point, not scattered per caller

**Status:** Accepted, implemented.

**Decision:** `is_suppressed(db, customer_id, phone_number)` checks both the per-customer `do_not_call` flag and an org-scoped, phone-hash-based `suppression_list` table. It is called from exactly one place that actually places a call (`start_outbound_call`), and additionally at both queue-advancement sites that decide *which* row becomes the next active call (`trigger_next_queued_call`'s loop, and `/calls/run-sheet`'s candidate-selection loop) — because a suppressed row must be skipped, not become the row that blocks the rest of the queue from advancing.

**Reason:** The campaign-automation feature was found broken for three compounding reasons: `customer_service.upsert_customer` and `google_sheets_service.update_sheet_status` did not exist as functions at all (confirmed via `grep` returning zero definitions anywhere in the codebase, despite being called), and `/calls/run-sheet` called `telephony_service.start_outbound_call` with a keyword argument (`customer_phone`) that did not match the function's actual parameter name (`phone_number`). Fixing the crash bugs alone would have restored dialing without restoring compliance — the explicit decision, confirmed with the product owner during design discussion, was to bundle do-not-call enforcement into the same fix rather than ship a working dialer with a silent compliance gap.

**Tradeoffs:** Slightly more complex candidate-selection logic in `/calls/run-sheet` (it must iterate candidates, upsert each into the CRM, check suppression, and mark suppressed sheet rows `do_not_call` before finding the first callable row) rather than a naive "take the first queued row."

**Alternative considered:** Fix only the crash bugs and enforce suppression solely inside `start_outbound_call`. Rejected because, in the queue-advancement loops specifically, that would have caused a suppressed lead to become the "active row" the loop waits on, silently stalling all subsequent leads in the sheet rather than skipping past them.

**Future review trigger:** If a second suppression mechanism (e.g., a customer-initiated opt-out webhook, or a legal/compliance-driven bulk suppression import) is added, confirm it writes to the same `suppression_list` table `is_suppressed` reads from, rather than creating a parallel, unchecked suppression path.

---

### ADR-010: Pin direct Python dependencies and verify them continuously

**Status:** Accepted and implemented on 2026-08-05.

**Decision:** Keep a reviewed list of exact direct production dependency versions in `app/requirements.txt`, derived from the known-working Python 3.11 repository environment. Use the frontend `package-lock.json` through `npm ci`. GitHub Actions installs both dependency sets and runs the backend regression suite and frontend production build on every push and pull request.

**Reason this matters:** Any fresh environment (a new engineer's machine, a CI runner, a production host) has no reproducible way to install the correct dependency set; version drift between the working local environment and any other environment is currently invisible until something breaks.

**Tradeoffs:** Exact direct pins make upgrades intentional and easy to review, but transitive packages are still resolved by pip for the target platform. If transitive drift becomes a demonstrated problem, add a platform-aware compiled lock/constraints process rather than committing a raw, workstation-specific `pip freeze`.

**Alternative considered:** A raw `pip freeze` was rejected because it would include transitive and workstation-specific packages that the application does not directly own. The manifest was hand-curated from actual imports and the known-working environment instead.

**Future review trigger:** Introduce a compiled, hash-locked dependency workflow if CI demonstrates transitive drift, supply-chain policy requires hashes, or multiple deployment platforms need independently reproducible lock sets.
