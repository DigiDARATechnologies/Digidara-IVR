-- Roll back only the observability column and Tamil quality setting overrides.
DELETE FROM system_settings WHERE setting_key IN (
  'openai_realtime_model_tamil',
  'openai_transcription_model_tamil',
  'openai_transcription_language_tamil',
  'tamil_barge_in_confirm_ms',
  'tamil_barge_in_min_voiced_frames',
  'openai_vad_eagerness_tamil',
  'tamil_core_knowledge_max_chars'
);

UPDATE system_settings
SET setting_value = 'adaptive_tamil_tanglish_tn_v6'
WHERE setting_key = 'tamil_voice_style_profile';

UPDATE system_settings
SET setting_value = 'tamil_validated_barge_in_v2'
WHERE setting_key = 'tamil_turn_gate_profile';

UPDATE system_settings
SET setting_value = 'tamil_voice_core_v1'
WHERE setting_key = 'tamil_knowledge_profile';

ALTER TABLE call_logs DROP COLUMN transcription_model;
