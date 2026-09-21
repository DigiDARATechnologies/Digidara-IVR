# DigiDARA — Operations Runbook

## Scope and Honest Baseline

This runbook covers both what exists today (a single developer-operated environment with manual monitoring) and the target operational posture once [ENGINEERING_ROADMAP.md](#) Epic G lands. Sections are marked accordingly.

## Monitoring

**Today:** No dedicated monitoring/alerting stack exists. Visibility into system health comes from: the FastAPI process's own console output, the Plivo dashboard (call logs, hangup source, billing), and direct database queries against `call_logs`/`realtime_usage`/`provider_callback_events`.

**Target:** At minimum, alert on: webhook signature-validation failure rate (a spike suggests either a misconfigured secret or an actual spoofing attempt), call-creation failure rate (a spike suggests a dead ingress/tunnel or a Plivo-side outage), and OpenAI Realtime WebSocket connection failures.

## Logging

Application logging today is console `print()`-based (e.g., `[GoogleSheets][ERROR]`, `[OpenAI Realtime][CONFIG ERROR]`, `[OpenAI Realtime] turn rejected | ...` prefixed messages), not a structured logging framework with levels/correlation. Existing correlation is achieved instead via the `correlation_id` generated per call attempt and threaded through webhook query parameters and `call_logs.correlation_id`, and via `event_id`/`event_key` uniqueness for idempotency. When diagnosing a specific call, search for its `correlation_id` (or `call_sid`) across `call_logs`, `call_events`, `conversations`, `realtime_usage`, and `provider_callback_events` — these five tables together reconstruct nearly everything that happened during that call.

## Incident Response

See [SECURITY_GUIDE.md](#) Incident Response for security-specific incidents (credential leak, suppression bypass, signature-validation failure spikes). Operational (non-security) incidents below.

### Provider Outage — Plivo

**Symptoms:** Call-creation requests fail or time out; `/answer`/`/hangup`/other webhooks stop arriving.
**Diagnosis:** Check Plivo's own status page; check whether `start_outbound_call`'s exception handling is recording `failed` call logs with a consistent `type(exc).__name__` (a consistent exception type across many failures in a short window points to a systemic Plivo-side issue rather than isolated per-call failures).
**Response:** No automatic failover to a second telephony provider exists today (the abstraction in `app/services/telephony/` exists specifically to make this possible in the future, but only one implementation exists now). During an outage, halt new outbound dialing (pause any active bulk-campaign trigger) rather than let calls fail silently into `call_logs` as `failed` rows indefinitely — a failed bulk-campaign row should be revisited once the outage clears, not treated as a permanent disposition.
**Recovery:** Resume dialing once Plivo's status page confirms recovery; spot-check a small number of calls before resuming full bulk-campaign volume.

### Provider Outage — OpenAI Realtime

**Symptoms:** `/ws/plivo/media` connections to OpenAI fail to establish, or established connections drop mid-call; customers hear silence or a dead line after Plivo's stream connects.
**Diagnosis:** Check `[OpenAI Realtime][CONFIG ERROR]`-prefixed logs; confirm `OPENAI_API_KEY` is valid and not rate-limited; check OpenAI's own status page.
**Response:** Same principle as a Plivo outage — pause new outbound dialing rather than let customers experience dead-air calls. There is no fallback conversational engine (the Twilio-era pipeline is not maintained as a hot standby and should not be assumed usable as an emergency fallback without significant verification).
**Recovery:** Resume once OpenAI's status page confirms recovery; run the smoke-test scenarios from [TESTING_STRATEGY.md](#)/[IMPLEMENTATION_CHECKLIST.md](#) Story C2 (once built) before resuming full volume.

### Database Outage

**Symptoms:** API requests fail with connection errors; `get_db`/`get_db_connection` raise.
**Diagnosis:** Confirm MySQL instance health and connectivity from the application host.
**Response:** The application has no request-queueing or graceful-degradation mode for a database outage today — it will fail requests directly. Communicate the outage; do not attempt to place calls during a database outage, since call-state tracking (idempotency, suppression checks) depends on it being available and correct.
**Recovery:** Once the database is restored, verify no in-flight calls were left in an inconsistent state (a call that was `initiated` in Plivo but whose status-update write to `call_logs` failed due to the outage) by cross-checking recent Plivo call history against `call_logs` for the outage window.

### Voice-Path Outage (Ingress/Tunnel Failure)

**Symptoms:** Calls connect (ring) but the AI never speaks; Plivo's webhook/stream requests fail to reach the backend.
**Diagnosis (development environment):** This is the single most common development-environment incident. Check whether the Cloudflare Quick Tunnel process is still running and whether `.env`'s `WEBHOOK_BASE_URL`/`PLIVO_STREAM_BASE_URL` still match its *current* hostname — the hostname changes on every tunnel restart, and a stale value causes call creation to fail with a Plivo `ValidationError` ("answer_url parameter is not valid"), which can look like a deeper application bug if the tunnel-restart cause isn't checked first.
**Response:** Restart the tunnel, update `.env` with the new hostname, restart the backend process to pick up the new value.
**Target-state prevention:** A stable, non-ephemeral ingress (Epic C / Epic G) eliminates this failure mode entirely for any non-local environment.

## Backup

**Today:** No documented, verified backup process for the MySQL instance exists in the repository. This is a gap that should close before the database holds any real, irreplaceable customer/campaign data at volume.
**Target:** Automated, regular backups of the managed database instance (once Epic G's managed-database item lands), with a documented, periodically-tested restore procedure — a backup that has never been restored from is not a verified backup.

## Recovery

For any incident above, the general recovery checklist is:

1. Confirm the root cause (do not assume; the tunnel-hostname failure mode above is exactly the kind of incident that looks like something else if not checked first).
2. Halt new outbound dialing if the issue affects call quality or correctness, rather than let it continue degrading customer experience or corrupting call-disposition data.
3. Fix the root cause.
4. Verify with a small number of test calls before resuming full volume.
5. Reconcile any state left inconsistent during the incident window (failed call_logs rows that should be retried, sheet rows left in an intermediate status, suppression-list writes that may have been missed).
6. Record what happened and what closes the gap permanently — an incident that recurs because its root cause was never actually fixed is a process failure, not a technology failure.
