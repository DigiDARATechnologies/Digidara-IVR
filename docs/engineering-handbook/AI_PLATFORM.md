# DigiDARA — AI Platform

## OpenAI Integration

The conversational engine is OpenAI's Realtime API, connected via WebSocket (`wss://api.openai.com/v1/realtime?model=...`) from `app/api/openai_realtime.py`. A separate, non-realtime call to OpenAI's TTS REST endpoint (`/v1/audio/speech`, model `gpt-4o-mini-tts`) is used once, offline from any live call, to pre-render the DTMF language-menu audio prompt (see [VOICE_PLATFORM.md](#)) — this is the only non-Realtime OpenAI usage in the live product surface. There is no `openai` Python SDK dependency installed; all OpenAI communication is done directly over `websockets` (Realtime) and `requests` (the one-off TTS call), which keeps the integration surface explicit and dependency-light.

Two Realtime model tiers are supported and billed differently: a full model (`gpt-realtime-2.1`) and a mini variant (`gpt-realtime-2.1-mini`), selected per call/language via configuration, with cost-rate tables (`_realtime_token_rates`) keyed on which tier actually served the call — recorded per call in `call_logs.realtime_model` and `realtime_usage.model_name` so historical cost analysis reflects the model actually used, not just whatever is configured today. English uses the mini model, while Tamil uses the full `gpt-realtime-2.1` model after two live mini calls showed unacceptable campaign-context adherence and false-termination behavior. Tamil retains its existing `gpt-4o-transcribe` transcription model, voice, prompt, and manual validated-turn policy.

## Conversation Memory

## Cost Estimation and Presentation

`app/services/usage_cost_service.py` estimates cost from the Realtime model that actually served the call, recorded in `call_logs.realtime_model` and `realtime_usage.model_name`. It separates cached from uncached audio/text input, clamps cached counts to the corresponding total input, and adds the separate transcription-model estimate. New and backfilled records carry `cost_estimation_version=openai_realtime_cache_aware_v1` in `realtime_usage.usage_data`. These values are operational estimates; provider invoices remain authoritative.

Billing presentation intentionally keeps providers separate. OpenAI estimates use `USD_TO_INR_RATE`; recorded Plivo USD API values use `PLIVO_USD_TO_INR_RATE`, matching the account's INR presentation. The dashboard must not describe the combined figure as an invoice or convert both providers through one exchange rate.

Two distinct memory mechanisms exist, serving different purposes:

- **Cross-call memory (`customer_memory`):** one row per customer, holding `intent`, `previous_questions`, `lead_status`, `summary`, `preferred_language`, and call counts. This is compacted (`compact_customer_memory`) and injected into the session instructions at the start of a new call, so the AI can reference what a returning customer previously asked or was told without replaying the full historical transcript.
- **Within-call transcript (`conversations`):** the raw, turn-by-turn record of the current call, persisted incrementally as the call progresses (`schedule_persist`), keyed by an idempotent `event_id` so a duplicate persistence attempt is a no-op.

The system does not currently maintain a running in-session "chat history" object the way a stateless chat API integration would — the Realtime API itself maintains conversation state server-side for the duration of the WebSocket connection; DigiDARA's own persistence layer exists for cross-call continuity and analytics, not for reconstructing the live conversation.

## Knowledge Retrieval

Knowledge is retrieved **per-turn, on demand**, not loaded wholesale into every session:

1. `should_retrieve_knowledge(customer_text, language)` classifies whether the customer's utterance actually needs a knowledge lookup (excluding greetings, acknowledgements, and terminal intents like `stop`/`callback`/`end_call`/`language_switch`), requiring at least two alphanumeric/Tamil-script tokens to bother retrieving at all.
2. If retrieval is warranted, the relevant knowledge chunks are pulled — for Tamil, from an in-memory BM25 index built at process startup over `knowledge_base_ta.py`/`knowledge_ta.txt`'s documents (visible in logs/test output as `[InMemoryKB] Loaded N ta documents into RAM` and `ta BM25 index built`); for English, from `get_fast_context("en")` and the broader `knowledge_base.py` corpus.
3. Retrieved content is formatted into the turn's instructions via `build_turn_knowledge_context` and injected as part of that turn's `session.update`/response instructions, not appended permanently to the system prompt — keeping per-turn token cost and the risk of the model surfacing stale or irrelevant context down.

A separate retrieval path (`app/api/rag.py`, `app/services/rag_service.py`) backs the in-app assistant/chat surface (`assistant_chat_messages`) and is independent of the live-call knowledge path — the two should not be assumed to share index freshness or content scope without explicit verification.

## Prompt Management

All conversational system-prompt construction lives in `app/services/conversation_policy_service.py`, split into composable builders:

- `build_shared_conversation_policy()` — universal rules: AI self-disclosure, the instruction to call the `end_call` tool immediately and silently when customer intent to end is clear, and the counter-rule that unclear/partial speech, noise, silence, or a request to repeat is never end intent and must receive one short clarification.
- `build_tamil_language_policy()` / `build_english_language_policy()` — per-language persona, register, and code-switching rules. The Tamil policy explicitly permits English loanwords for course/technical terms (course, fees, batch, online, offline, job, internship, etc.) while instructing the model *not* to fully switch to English merely because such a term appeared. The English policy uses slow, neutral, easy-to-understand Indian English with familiar words and an 8–20-word one-sentence default; it permits a second sentence only when essential, caps the normal turn at about 28 words, and remains in English unless the customer explicitly requests Tamil.
- `build_initial_session_instructions()` — assembles the full first-turn instruction set (shared policy + language policy + campaign context + customer context) for a new session.
- `build_existing_english_session_instructions()` — a separate, more detailed English-specific instruction template used to preserve an already-established consultative-sales conversation flow, including campaign-prompt token substitution (`{customer_name}`, `{language}`, etc.) and an explicit `<untrusted_campaign_content>` boundary around the campaign's own `ai_prompt` text.
- Prompt length is treated as a real engineering constraint, not an afterthought: `tests/test_conversation_policy_service.py` and `tests/test_tamil_conversation_service.py` assert token-budget ceilings on the static policy text (verified via an `estimate_prompt_tokens` helper), so a prompt edit that grows the static policy past its budget fails CI/test rather than silently inflating every session's token cost.

Prompt changes are, in practice, behavior changes with the same blast radius as code changes — two of the conversational bugs found and fixed during the current engineering pass were pure prompt-wording issues (the over-broad English-switch instruction above, and the initial DTMF-menu implementation relying on Plivo's native `<Speak>`, which cannot render Tamil at all). See [ENGINEERING_GUIDELINES.md](#) for the resulting review discipline.

## Tool Architecture

Exactly one tool is defined today: `end_call`, declared in the Realtime session's `tools` array with `tool_choice: "auto"` and a description instructing the model to invoke it silently, mid-turn, based on its own judgment of customer intent — not on an exact matched phrase. Its contract explicitly excludes unclear, partial or unintelligible speech, silence/noise, and requests to repeat or clarify.

Tool-call handling flow:

1. OpenAI emits `response.output_item.done` with `type: "function_call"`, `name: "end_call"`, and a JSON `arguments` payload (a `reason` field).
2. The bridge parses the reason, persists it to `call_logs.conversation_end_reason`, and applies any compliance side effects (setting `do_not_call`/inserting into `suppression_list` if the reason indicates the customer does not want to be called again), storing `pending_tool_call = (call_id, reason)`.
3. On the subsequent `response.done` event, if a tool call is pending, the bridge submits a `conversation.item.create` of type `function_call_output` (satisfying the Realtime API's requirement that a function call be acknowledged with an output before the conversation continues), sets `customer_requested_end = True`, and issues a new `response.create` with `instructions: farewell_instruction(response_language)` so the model delivers one short, warm goodbye in the correct language before the call is hung up.
4. Only after that farewell turn completes (`response.done` with no new pending tool call, and no other in-flight response items) does `schedule_graceful_customer_hangup()` actually end the call — this two-step sequencing (acknowledge tool call → let the model say goodbye → then hang up) is what makes the termination feel like a natural conversational close rather than an abrupt cutoff.

Regex/keyword-based intent classification (`conversation_end.py`, `classify_intent`'s `stop`/`not_interested`/`end_call` categories) remains active in parallel, used for structured CRM disposition tagging (do-not-call flag, lead status) and as a defense-in-depth signal, but the authoritative decision to actually end the call is the model's tool call, not the regex match — this was an explicit, user-driven architectural correction after keyword patterns were repeatedly found to miss real phrasings in live testing (see [ARCHITECTURE_DECISION_RECORD.md](#) ADR-004).

## Future Providers

The Realtime bridge (`app/api/openai_realtime.py`) is not currently behind a provider-neutral interface the way telephony is (`app/services/telephony/`) — it is written directly against OpenAI's Realtime protocol. `app/services/gemini_service.py` and `app/services/sarvam_service.py` exist in the codebase with their own `text_to_speech_async` implementations (used by an earlier, non-Realtime Twilio-era pipeline still present but not the active production path — see `app/services/twilio_service.py`, `app/api/conversation_relay.py`), which means the codebase already has direct experience integrating at least two alternative TTS providers, even though neither is wired into the current live call flow. If a second Realtime-capable provider becomes a real requirement, extracting a thin interface analogous to `get_telephony_provider()` — covering session establishment, audio streaming, and tool-call handling — is the natural next step; building that abstraction speculatively before a second provider is actually needed would violate the "no speculative abstraction" principle in [ENGINEERING_GUIDELINES.md](#).

## Evaluation Strategy

Today's "evaluation" is cost/latency/quality telemetry recorded per call (`call_logs`'s latency percentiles, `false_turn_count`, `interruption_count`, `stt_confidence_avg`) plus manual review of live/recorded calls. Response latency is measured from the last locally observed voiced caller frame to the first assistant audio sent to Plivo, so it includes semantic-VAD turn-finalization wait as well as model response time. There is no automated conversation-quality scoring (e.g., rubric-based transcript evaluation, or regression testing against a fixed set of expected conversational behaviors). Given that real conversational bugs have only been caught by a human listening to live test calls, building at least a lightweight automated evaluation pass is a near-term priority; see [ENGINEERING_ROADMAP.md](#) Epic F and [TESTING_STRATEGY.md](#).
