# Plivo production release checklist

## Automated

- [x] Python source compilation
- [x] Provider/protocol/Tamil unit suite
- [x] TypeScript production build
- [x] Mocked outbound request contract
- [x] Status normalization
- [x] μ-law `playAudio`, checkpoint, and `clearAudio` frames
- [x] HMAC stream-context validation

## Deployment

- [ ] Back up MySQL
- [ ] Apply `migrations/20260727_plivo_provider_up.sql`
- [ ] Install `app/requirements.txt`
- [ ] Set real Plivo credentials in the secret manager
- [ ] Set stable public HTTPS and WSS URLs
- [ ] Keep `PLIVO_VALIDATE_SIGNATURES=true`
- [ ] Configure Plivo number/application callbacks
- [ ] Confirm India KYC, geo permissions, caller ID, and recording consent

## Live verification (requires paid credentials)

- [ ] Outbound English call
- [ ] Outbound Tamil AI/ML enquiry follow-up
- [ ] Exactly one greeting and one voice per call
- [ ] Caller silence does not generate an answer
- [ ] Tamil/Tanglish questions receive query-matched answers
- [ ] Barge-in clears queued Plivo audio
- [ ] busy, no-answer, rejected, and failed calls normalize correctly
- [ ] duplicate hangup and recording callbacks have one side effect
- [ ] stereo recording plays only through the authenticated backend proxy
- [ ] Plivo CDR billed duration and amount appear in billing
- [ ] sheet queue advances once
- [ ] restart recovery closes stale active calls

Automated tests cannot prove PSTN routing, credentials, KYC, public TLS, live
voice quality, carrier latency, recording readiness, or actual provider billing.
