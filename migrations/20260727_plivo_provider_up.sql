-- Apply after taking a database backup. This mirrors schema.sql and init_db().
ALTER TABLE call_logs
  ADD COLUMN provider VARCHAR(32) NOT NULL DEFAULT 'plivo' AFTER call_sid,
  ADD COLUMN provider_request_id VARCHAR(255) NULL,
  ADD COLUMN provider_call_id VARCHAR(255) NULL,
  ADD COLUMN provider_stream_id VARCHAR(255) NULL,
  ADD COLUMN provider_recording_id VARCHAR(255) NULL,
  ADD COLUMN provider_status VARCHAR(64) NULL,
  ADD COLUMN stream_status VARCHAR(64) NULL,
  ADD COLUMN correlation_id VARCHAR(64) NULL,
  ADD COLUMN provider_metadata LONGTEXT NULL,
  ADD COLUMN estimated_telephony_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0,
  ADD COLUMN provider_bill_duration_seconds INT NOT NULL DEFAULT 0,
  ADD UNIQUE INDEX uq_call_provider_id (provider,provider_call_id),
  ADD UNIQUE INDEX uq_call_correlation (correlation_id),
  ADD INDEX idx_call_provider_request (provider,provider_request_id);

UPDATE call_logs SET provider='twilio',provider_call_id=call_sid,
 provider_stream_id=stream_sid,provider_recording_id=recording_sid,
 estimated_telephony_cost_usd=estimated_twilio_cost_usd
WHERE call_sid LIKE 'CA%' OR estimated_twilio_cost_usd > 0;

CREATE TABLE provider_callback_events (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, provider VARCHAR(32) NOT NULL,
 event_type VARCHAR(100) NOT NULL,event_key VARCHAR(255) NOT NULL,
 call_log_id INT NULL,payload LONGTEXT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_provider_callback (provider,event_type,event_key),
 INDEX idx_provider_callback_call (call_log_id),
 FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
