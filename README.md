# DigiDARA AI Communications

Production-oriented, multi-tenant bilingual voice communications platform. Plivo provides
inbound/outbound telephony and bidirectional
8 kHz μ-law streaming. OpenAI Realtime remains the speech-to-speech engine for
both English and conversational Tamil.

## Current architecture

```text
Voice Operations Dashboard
  -> existing signed call transport identifiers
  -> provider-neutral telephony_service
  -> Plivo Calls API
  -> signed /api/plivo/answer callback
  -> <Record recordSession="true"> + bidirectional <Stream>
  -> /ws/plivo/media
  <-> OpenAI Realtime (G.711 μ-law, 8 kHz)
  -> signed lifecycle/stream/recording callbacks
  -> call_logs, summaries, usage, recordings
```

The answer XML contains no carrier `<Speak>` greeting. OpenAI Realtime owns the
single welcome message and the selected English/Tamil voice, preventing double
greetings and voice changes. Plivo `checkpoint`, `playedStream`, `clearAudio`,
and `clearedAudio` events support playback tracking and barge-in.

## Local setup

Requirements: Python 3.11+, Node 20+, MySQL 8+, a Plivo voice number, an OpenAI
API key, and a public HTTPS/WSS URL for real calls.

```powershell
Copy-Item .env.example .env
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r app\requirements.txt
npm install
```

Create the database from `schema.sql`, then run:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
python -m app.workers.crm_delivery_worker
npm run dev
```

Run the CRM worker as a separate process whenever CRM delivery is enabled. In
container deployments, `docker compose up --build` starts the API, worker, and
MySQL services together. The Facility Operations console remains an isolated
module under its own route.

For deployment orchestration, `/health/live` confirms the API process is
running and `/health/ready` confirms MySQL can be queried. Administrators can
use Security Center to view secret-safe production checks and the CRM worker
heartbeat; no endpoint returns credential values.

Open `http://localhost:5173`. Without complete Plivo credentials and a public
`WEBHOOK_BASE_URL`, outbound initiation intentionally creates a simulated call
log and does not place a paid call.

## Plivo configuration

Set these values in `.env`:

```dotenv
TELEPHONY_PROVIDER=plivo
PLIVO_AUTH_ID=...
PLIVO_AUTH_TOKEN=...
PLIVO_FROM_NUMBER=+91...
WEBHOOK_BASE_URL=https://voice.example.com
PLIVO_STREAM_BASE_URL=wss://voice.example.com
PLIVO_VALIDATE_SIGNATURES=true
PLIVO_STREAM_TOKEN_SECRET=a-long-random-secret
PLIVO_INBOUND_LANGUAGE=tamil
```

Install the backend dependencies in the same virtual environment used to start
Uvicorn:

```powershell
.\venv\Scripts\python.exe -m pip install -r app\requirements.txt
```

`PLIVO_FROM_NUMBER` must be an account-owned E.164 number without spaces, for
example `+912269985448`. `WEBHOOK_BASE_URL` and `PLIVO_STREAM_BASE_URL` normally
use the same public tunnel hostname with `https://` and `wss://` respectively.
Restart Uvicorn after changing `.env` or installing the Plivo SDK.

Which organization/campaign an inbound call routes to is no longer a single
global env var — register each Plivo DID your business owns via
`POST /phone-numbers` (`campaign_id`, `plivo_number`, optional `label`).
`/api/plivo/inbound` looks up the dialed number there and rejects calls to
any number that hasn't been registered.

HTTP callbacks always use Plivo V3 signature validation. The media WebSocket is
authenticated by a server-generated HMAC token bound to the customer, campaign,
correlation ID, and a recent active Plivo call row. This survives Cloudflare and
ngrok WebSocket URL canonicalization without exposing the stream endpoint.
Keep `PLIVO_VALIDATE_WEBSOCKET_SIGNATURES=false` behind those tunnels. A direct
production deployment whose proxy preserves Plivo's exact signed upgrade URL
may opt in with `PLIVO_VALIDATE_WEBSOCKET_SIGNATURES=true`.

Keep `PLIVO_STREAM_BASE_URL` as `wss://`; do not change it to `https://`.

Configure the Plivo number/application answer URL for inbound traffic to
`/api/plivo/inbound`; it maps the caller to the configured campaign and redirects
into the same Realtime flow. Outbound calls set their
answer, ring, hangup, and fallback URLs through the API automatically.

All HTTP callbacks are validated with Plivo V3 signature, signature nonce, the
exact public callback URL, HTTP method, parameters, and `PLIVO_AUTH_TOKEN`.
Signature bypass is accepted only when both conditions hold:

```dotenv
ENVIRONMENT=development
PLIVO_VALIDATE_SIGNATURES=false 
```

Production always validates. The media socket also requires an HMAC session
token. Do not log authorization headers, signatures, raw media, or full webhook
payloads.

## Provider-neutral data model

New code writes `provider`, `provider_request_id`, `provider_call_id`,
`provider_stream_id`, `provider_recording_id`, `provider_status`,
`stream_status`, `correlation_id`, `provider_metadata`,
`estimated_telephony_cost_usd`, and `provider_bill_duration_seconds`.

Historical `call_sid`, `stream_sid`, `recording_sid`, and
`estimated_twilio_cost_usd` remain for compatibility. Existing Twilio rows are
backfilled as `provider='twilio'`; new calls are Plivo. Callback side effects
are deduplicated in `provider_callback_events`.

Migration files:

- `migrations/20260727_plivo_provider_up.sql`
- `migrations/20260727_plivo_provider_down.sql`

`schema.sql` and the safe startup migration in `app/database/db.py` contain the
same production schema. Back up MySQL before a manual migration.

The shared English/Tamil conversation refactor adds no new columns. Callback,
disposition and opt-out actions reuse `call_logs.followup_required`,
`call_logs.lead_status`, `call_logs.conversation_end_reason`,
`customers.do_not_call` and `suppression_list`. Per-call intent, cancellation
and response-length metrics are stored in the existing
`realtime_usage.usage_data` JSON. `schema.sql` documents these uses and remains
the source of truth for an idempotent utf8mb4 deployment.

## Call lifecycle

Normalized states are `initiated`, `ringing`, `in-progress`, `completed`,
`busy`, `no-answer`, `canceled`, and `failed`. Plivo callbacks may be retried;
the application uses provider IDs plus event type as idempotency keys. Terminal
finalization reuses an existing summary and cannot trigger campaign queue
progression twice.

Recording is session-wide stereo MP3. The Plivo `<Record>` element explicitly
uses a 14,400-second maximum so it does not stop at Plivo's 60-second default.
The UI never receives provider
credentials or a raw provider URL: it loads audio through
`GET /calls/logs/{id}/recording`. Billing uses the Plivo CDR’s billed duration
and total amount when available; it does not hardcode carrier prices.

Completed calls are analysed from the complete two-sided transcript. Groq is
used when configured; otherwise the existing OpenAI API key and
`OPENAI_CHAT_MODEL` are used. Call History stores and displays three or four
factual lines: customer need, discussion, outcome, and next action.

## Facility voice behavior

The active Plivo/OpenAI Realtime transport is unchanged. Its system prompt is
now `nectar_facility_operations_voice_v1`: it loads only a tenant-scoped
facility asset/alert snapshot and Facility RAG procedures. It never loads the
legacy sales campaign prompt, course enquiry fields, sales playbook, or sales
knowledge base.

The assistant handles asset status, alerts, energy/sensor readings, approved
procedures, and maintenance-request preparation. It cannot create a request by
voice: the operator must use the Facility Console and explicitly confirm the
action. Unsupported questions receive an honest no-evidence response.

Tamil uses `shared_query_first_phone_v1`: raw audio and ASR pass the noise/echo
gate, then an `asyncio.Lock` and monotonically increasing turn ID allow only the
newest validated customer turn to create a response. Tamil factual questions
retrieve at most three relevant BM25 chunks capped at 1,800 characters;
administrative turns retrieve none. Its 48 reviewed spoken-Tamil chunks cover
the English fact areas.

Tamil's two-stage barge-in sends Plivo `clearAudio`, OpenAI `response.cancel`
once, and `conversation.item.truncate` at acknowledged playback time. English
retains its earlier immediate semantic-VAD interruption behavior. In both
paths, audio and transcripts belonging to an interrupted response are ignored.

Tamil uses `OPENAI_VAD_EAGERNESS_TAMIL=medium`; English keeps its established
automatic flow with `OPENAI_VAD_EAGERNESS_ENGLISH=high`.

Prompt sizes are recorded as count-only estimates in
`realtime_usage.usage_data`; full prompts and private memory are not stored.
The estimator is conservative for Tamil and is not a billing meter. Actual text,
audio, cached-input and total tokens come from OpenAI Realtime usage events.

`call_logs.avg_response_latency_ms` records customer-perceived response latency.

The assistant identifies itself as an AI voice assistant in its only greeting,
then waits. It does not restart the welcome, speak without accepted caller
speech, or repeat a previous answer unless asked.

Choose Tamil and English model values according to the deployment's quality,
latency and cost targets, then test them before production. Every call stores
the actual resolved model in `call_logs.realtime_model`.
The ASR model used for the call is stored in
`call_logs.transcription_model`.
Realtime cost estimates use the shared `OPENAI_*_USD_PER_M` settings; provider
invoices remain authoritative.

`OPENAI_REALTIME_VOICE_TAMIL_CUSTOM_ID` and
`OPENAI_REALTIME_VOICE_ENGLISH_CUSTOM_ID` are optional. A valid OpenAI custom
voice ID such as `voice_...` is sent as `{ "id": "voice_..." }` before the first
audio response. URLs, local audio paths and unrelated provider IDs are rejected.
Otherwise the corresponding built-in voice variable is used.

Tamil explicit goodbye/end requests use the validated graceful Plivo closing
flow. English keeps its established consultative closing behavior. A standalone
“thank you” or “நன்றி” is not treated as an opt-out.

## Tests and verification

```powershell
python -m unittest discover -s tests -q
npm run build
```

Provider tests use mocked Plivo clients and do not place paid calls. Before
production release, verify with a real Plivo account and public TLS endpoint:
outbound answer/ring/hangup, inbound routing, Tamil and English audio,
interruption, duplicate callbacks, recording playback, CDR cost, no-answer,
busy, queue progression, and worker restart recovery.

## Rollback

1. Stop new call initiation.
2. Let active Plivo calls finish or terminate them through the application.
3. Preserve a database backup and provider callback logs.
4. Roll back the application release.
5. Run the down migration only if the prior release cannot tolerate the new
   columns. It intentionally leaves historical compatibility columns intact.

There is no active Twilio router or Twilio SDK dependency in this release.
Legacy source modules and historical columns may be retained temporarily for
audit/rollback, but the registered runtime path is Plivo.
