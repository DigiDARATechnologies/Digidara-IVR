-- Apply after taking a database backup. Mirrors schema.sql and init_db().
ALTER TABLE call_logs
  ADD COLUMN transcription_model VARCHAR(100) NULL AFTER realtime_model;

INSERT INTO system_settings (setting_key, setting_value, is_secret) VALUES
  ('openai_realtime_model_tamil', 'gpt-realtime-2.1', FALSE),
  ('openai_transcription_model_tamil', 'gpt-4o-transcribe', FALSE),
  ('openai_transcription_language_tamil', '', FALSE),
  ('tamil_voice_style_profile', 'natural_tamil_tn_query_first_v7', FALSE),
  ('tamil_knowledge_profile', 'tamil_semantic_parity_v2', FALSE),
  ('tamil_turn_gate_profile', 'tamil_fast_semantic_barge_in_v4', FALSE),
  ('tamil_barge_in_confirm_ms', '80', FALSE),
  ('tamil_barge_in_min_voiced_frames', '2', FALSE),
  ('openai_vad_eagerness_tamil', 'medium', FALSE),
  ('tamil_core_knowledge_max_chars', '4200', FALSE)
ON DUPLICATE KEY UPDATE
  setting_value = VALUES(setting_value),
  is_secret = VALUES(is_secret);
