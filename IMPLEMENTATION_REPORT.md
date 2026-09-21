# Shared English/Tamil realtime counsellor report

## English-flow restoration amendment

The later bilingual refactor changed the already-working English conversation
from automatic Realtime turn handling to the new Tamil manual planner. That
altered English discovery questions and sales progression. English has now been
restored to its established behavior:

- `consultative_education_sales_v2` campaign/customer sales instructions;
- complete approved English knowledge context at session start;
- automatic OpenAI semantic-VAD response creation and interruption;
- immediate Plivo playback clearing when the English caller speaks;
- the existing English greeting and natural Indian-English sales style.

Tamil remains on the new validated latest-turn planner, per-turn retrieval,
two-stage noise protection, explicit cancellation/truncation and Tamil/Tanglish
register matching. No database structure changed; the existing profile columns
identify which language workflow handled each call.

## 1–4. Root causes and active flow

1. Tamil was carrying a large permanent style/sales prompt plus broad knowledge
   before the caller asked a question. Formal source wording and duplicated
   instructions encouraged long, newsreader-like answers.
2. The English regression was caused by replacing its successful automatic
   consultative flow with Tamil's manual short-answer planner. That replacement
   has been reversed for English.
3. Interruption handling was inconsistent by language. English could clear
   playback on a speech event without the same sustained-audio validation,
   response-ID suppression and newest-turn guard. `response.cancel` alone also
   cannot remove audio already queued at Plivo.
4. The confirmed production path is:

   `UI /calls/start -> app/api/call.py -> telephony_service -> Plivo Calls API
   -> app/api/plivo.py answer XML -> /ws/plivo/media in
   app/api/openai_realtime.py -> OpenAI Realtime -> Plivo
   playAudio/checkpoint -> signed Plivo status/recording callbacks ->
   call_logs, conversations and realtime_usage -> campaign queue`.

   The answer XML uses one Plivo recording and bidirectional audio stream; it
   does not create a second carrier greeting voice. Duplicate provider
   callbacks are claimed idempotently. The historical `/media-stream/...`
   Twilio handler is not the active Plivo media path.

## 5–8. Shared architecture and files

5. `app/services/conversation_policy_service.py` contains the Tamil
   latest-question policy and an isolated builder for the restored English
   consultative session. The route selects one workflow from customer language.
6. Created:

   - `app/services/conversation_policy_service.py`
   - `tests/test_conversation_policy_service.py`

7. Modified:

   - `app/api/openai_realtime.py`
   - `app/services/tamil_conversation_service.py`
   - `app/services/realtime_input_gate.py`
   - `.env.example`
   - `schema.sql`
   - `README.md`
   - `tests/test_openai_realtime.py`
   - `tests/test_tamil_conversation_service.py`
   - `IMPLEMENTATION_REPORT.md`

8. No production file was removed. The large Tamil static policy was replaced
   by a compatibility wrapper around the shared policy. Historical Twilio code
   remains only for rollback/legacy routes and was not connected to the active
   Plivo flow.

## 9. Database behavior

No new database column was required. The implementation deliberately reuses:

- `call_logs.followup_required`, `lead_status` and
  `conversation_end_reason` for callback, not-interested and end requests;
- `customers.do_not_call` and `suppression_list` for idempotent opt-out;
- existing latency, interruption, model, voice and token columns;
- `realtime_usage.usage_data` for latest intent, latest turn, cancelled
  responses, stop/callback/end counters, average/maximum response words,
  limit violations and short-response compliance.

`schema.sql` documents these uses and continues to define every referenced
field/table with utf8mb4. Because the shape did not change, `app/database/db.py`,
ORM models, API schemas and frontend types did not need a migration change.
The real `.env` was not edited.

## 10–12. Prompt and response length

10. The previously measured Tamil construction was approximately 5,000
    conservative estimated tokens. The old English path could add up to 7,000
    knowledge characters (roughly 1,750 tokens before its other context).
    With a representative AI/ML follow-up campaign, the new exact estimator
    reports:

    | Layer | Estimated tokens |
    |---|---:|
    | Shared policy | 317 |
    | Tamil style | 241 |
    | English style | 95 |
    | Tamil initial prompt total | 672 |
    | Restored English knowledge context | 1,417 |
    | Restored English initial prompt total | 3,015 |

    Initial prompts contain no full knowledge base. Factual turns retrieve at
    most three relevant chunks, capped at 1,800 characters; administrative
    turns retrieve zero knowledge.
11. Tamil receives the compact per-turn instruction: answer the latest question,
    prefer one short sentence, use a second only when necessary, ask at most one
    question, and target 12–30 spoken words. Spoken-Tamil/Tanglish register
    matching is retained.
12. English again uses its original automatic semantic-VAD conversation and
    consultative sales playbook. Tests verify the language split; real model
    speech behavior still requires staged calls.

## 13–19. Runtime control

13. Tamil barge-in state machine:

    `speech_started -> collect configurable RMS frames -> reject noise OR
    confirm voiced speech -> mark response/item interrupted -> Plivo clearAudio
    -> OpenAI response.cancel once -> conversation.item.truncate at acknowledged
    playback ms -> suppress future interrupted response audio/transcript ->
    validate completed caller audio+ASR -> increment latest turn -> create one
    newest-turn response`.
14. Stop/pause support includes English `stop`, `wait`, `hold on`,
    `let me speak`, `listen`, `one minute`, `enough`; Tamil `நிறுத்துங்க`,
    `போதும்`, `ஒரு நிமிஷம்`, `கொஞ்சம் இருங்க`, `நான் பேசுறேன்`,
    `முதல்ல கேளுங்க`; and the requested Tanglish variants.
15. End support includes goodbye phrases plus `hang up`, `end/disconnect the
    call`, `call cut பண்ணுங்க`, standalone `வேண்டாம்/வேணாம்`, not-interested
    phrases and do-not-call/remove-number phrases. A phrase such as
    `Course வேண்டாம், internship சொல்லுங்க` is not misclassified as a call end.
16. Callback support includes busy, later, tomorrow and evening variants in
    English, Tamil and Tanglish. A stated time is confirmed; otherwise only one
    callback-time question is requested.
17. Plivo playback cancellation uses `clearAudio`, then playback checkpoints
    identify the acknowledged millisecond used for truncation.
18. OpenAI events use `response.cancel` once per active response and
    `conversation.item.truncate` with `item_id`, `content_index=0` and
    `audio_end_ms`. Deltas and completed transcripts from interrupted response
    IDs are ignored.
19. Semantic VAD automatic response creation remains enabled for English.
    Tamil disables it and uses one `asyncio.Lock`, `response_in_progress`, a
    monotonically increasing turn ID and a newest-only pending deque to prevent
    overlapping or stale `response.create` events.

## 20–22. Verification

20. Commands executed:

    - bundled Python `-m compileall -q app tests`
    - bundled Python `-m unittest discover -s tests -p 'test_*.py' -v`
    - bundled Python `-m pytest -q`
    - `npm.cmd run build`
    - repository searches for duplicate response creation, cancellation,
      full-KB injection, stale provider paths and prompt logging
21. Results:

    - compileall: passed
    - unittest: 74 passed
    - production frontend build: passed; TypeScript and Vite completed,
      2,034 modules transformed
    - pytest: unavailable in the usable bundled Python (`No module named
      pytest`); the repository virtual environment still points to a removed
      interpreter
    - lint: no lint script is configured in `package.json`
22. No live paid Plivo call was placed. Staging must still verify real Tamil,
    Tanglish, mixed and English audio; mid-word interruption; quiet short
    replies; echo/noise; callback and opt-out persistence; recording duration;
    duplicate callbacks; no-answer/busy; billing; queue progression; and worker
    restart recovery.

## 23–25. Deployment, rollback and limits

23. Back up MySQL; deploy the source; create a fresh Python environment; install
    `app/requirements.txt`; copy only the new non-secret settings from
    `.env.example`; run the idempotent schema initializer; run the frontend
    production build; restart FastAPI/workers; then perform staged Plivo calls
    before enabling campaigns.
24. To roll back, stop new campaign execution, allow or safely terminate active
    calls, preserve DB/provider callback logs, restore the prior application
    release and restart services. There is no destructive down migration for
    this change because no columns were added.
25. Telephone audio quality, network delay, model access and the selected
    built-in/custom voice still affect perceived naturalness. Token counts are
    conservative estimates until OpenAI returns actual usage. Prompt rules
    strongly constrain length, but the compliance metric—not crude audio/text
    truncation—detects occasional model violations.
