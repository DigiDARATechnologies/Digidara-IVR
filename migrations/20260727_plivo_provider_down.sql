-- Rollback removes only neutral migration data; historical Twilio columns remain.
DROP TABLE IF EXISTS provider_callback_events;
ALTER TABLE call_logs
  DROP INDEX uq_call_provider_id,
  DROP INDEX uq_call_correlation,
  DROP INDEX idx_call_provider_request,
  DROP COLUMN provider_bill_duration_seconds,
  DROP COLUMN estimated_telephony_cost_usd,
  DROP COLUMN provider_metadata,
  DROP COLUMN correlation_id,
  DROP COLUMN stream_status,
  DROP COLUMN provider_status,
  DROP COLUMN provider_recording_id,
  DROP COLUMN provider_stream_id,
  DROP COLUMN provider_call_id,
  DROP COLUMN provider_request_id,
  DROP COLUMN provider;
