# Plivo migration inventory

## Pre-migration runtime map

| Concern | Previous implementation | Migrated implementation |
|---|---|---|
| Outbound call creation | `app/services/twilio_service.py` | `app/services/telephony_service.py` and `app/services/telephony/plivo_provider.py` |
| Answer instructions | `/voice/welcome` in `app/api/call.py` | signed `/api/plivo/answer` in `app/api/plivo.py` |
| Live audio | Twilio `media`, `mark`, and `clear` frames | Plivo `media`, `playAudio`, `checkpoint`, and `clearAudio` |
| AI speech | OpenAI Realtime | OpenAI Realtime, unchanged |
| Lifecycle callbacks | `/webhook/twilio` | signed ring, hangup, stream, recording, and fallback Plivo callbacks |
| Call IDs | `call_sid`, `stream_sid`, `recording_sid` | neutral provider request/call/stream/recording IDs with legacy aliases |
| Billing | `estimated_twilio_cost_usd` | Plivo CDR `total_amount` and billed duration |
| Recording playback | direct Twilio REST fetch in route | authenticated provider adapter and backend proxy |
| Queue progression | Twilio service callback | provider-neutral service after idempotent finalization |
| Frontend | Call SID and Twilio cost labels | provider call ID and Plivo/telephony cost |

## Preserved product behavior

- English and Tamil OpenAI Realtime voice paths
- Tamil speech gate, conversational style, knowledge retrieval, and sales policy
- customer/campaign CRM linkage
- transcripts, two-to-three-detail summaries, lead qualification, and memory
- Google Sheets queue progression
- authenticated frontend recording playback

## Historical compatibility

The legacy SID and Twilio-cost columns are intentionally retained and
backfilled into the neutral schema. Legacy Twilio routers are not registered in
`app/main.py`; historical source files remain available for audit and rollback.
