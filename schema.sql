-- DigiDara Technologies - AI Calling Agent System
-- MySQL Database Schema
-- Language-isolated realtime voice release notes:
-- * customers.language selects the Tamil or English runtime profile.
-- * English preserves the established automatic semantic-VAD sales flow;
--   Tamil uses validated latest-turn response creation and per-turn retrieval.
-- * call_logs.realtime_voice records the built-in or custom voice actually used.
-- * call_logs.interruption_count measures caller barge-ins handled with playback
--   truncation, making repeat/mismatch regressions observable per call.
-- * call_logs voice, knowledge, conversation and turn-gate profiles record
--   the exact runtime behavior versions used for each call.
-- * existing follow-up/disposition/suppression fields handle callback, end-call
--   and do-not-call intents; realtime_usage.usage_data holds the new bilingual
--   response-length and cancellation metrics, so no new columns are required.

CREATE DATABASE IF NOT EXISTS digidara_voice_ai;
USE digidara_voice_ai;

-- SaaS tenant boundary. Every production user and business record belongs to
-- exactly one organization. Application queries must always scope by this id.
CREATE TABLE IF NOT EXISTS organizations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(180) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    plan_code VARCHAR(50) NOT NULL DEFAULT 'professional',
    monthly_call_limit INT NOT NULL DEFAULT 10000,
    data_retention_days INT NOT NULL DEFAULT 90,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO organizations (id, name, slug) VALUES (1, 'DigiDara Technologies', 'digidara')
ON DUPLICATE KEY UPDATE name=VALUES(name);

CREATE TABLE IF NOT EXISTS app_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    email VARCHAR(190) NOT NULL,
    password_hash VARCHAR(255) NULL,
    full_name VARCHAR(150) NOT NULL,
    role_code VARCHAR(30) NOT NULL DEFAULT 'agent',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    locked_until DATETIME NULL,
    last_login_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_tenant_email (organization_id,email),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    INDEX idx_user_role (organization_id,role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Stores the authenticated dashboard assistant conversation. The chatbot
-- receives aggregate operational data only; customer PII is deliberately not
-- inserted into its prompt or this table by the assistant endpoint.
CREATE TABLE IF NOT EXISTS assistant_chat_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL DEFAULT 1,
    user_id INT NOT NULL,
    role VARCHAR(20) NOT NULL, -- 'user' or 'assistant'
    message TEXT NOT NULL,
    page_path VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
    INDEX idx_assistant_chat_user_created (user_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1. campaigns table
-- Stores objective, name, and AI prompt template instructions for different phone campaigns.
CREATE TABLE IF NOT EXISTS campaigns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL DEFAULT 1,
    campaign_name VARCHAR(255) NOT NULL,
    objective TEXT NOT NULL,
    ai_prompt LONGTEXT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_campaign_status (organization_id,status),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1b. phone_numbers table
-- Maps a Plivo DID to the organization (and inbound campaign) that owns it,
-- so /api/plivo/inbound can route a call by the number actually dialed
-- instead of a single global PLIVO_INBOUND_CAMPAIGN_ID env var.
CREATE TABLE IF NOT EXISTS phone_numbers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    campaign_id INT NOT NULL,
    plivo_number VARCHAR(20) NOT NULL,
    label VARCHAR(120) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_phone_numbers_number (plivo_number),
    INDEX idx_phone_numbers_org (organization_id),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1c. business_hours table
-- Per-organization weekly schedule gating inbound calls, checked in
-- organizations.timezone-local time. No rows for an organization means
-- "always open" (fail-open) until it configures a schedule.
CREATE TABLE IF NOT EXISTS business_hours (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    day_of_week TINYINT NOT NULL COMMENT '0=Monday .. 6=Sunday',
    is_closed BOOLEAN NOT NULL DEFAULT FALSE,
    open_time VARCHAR(5) NULL COMMENT '24-hour HH:MM, organization-local time',
    close_time VARCHAR(5) NULL COMMENT '24-hour HH:MM, organization-local time',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_business_hours_org_day (organization_id, day_of_week),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. customers table
-- Stores details of students or customers to dial, populated from Google Sheets.
CREATE TABLE IF NOT EXISTS customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL DEFAULT 1,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NULL,
    phone VARCHAR(30) NOT NULL,
    language VARCHAR(20) NOT NULL DEFAULT 'english',
    investigated_course VARCHAR(255) NULL,
    internship_or_course VARCHAR(100) NULL,
    course_duration VARCHAR(100) NULL,
    sheet_url VARCHAR(500) NULL,
    sheet_row INT NULL,
    customer_status VARCHAR(50) NOT NULL DEFAULT 'new',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    consent_status VARCHAR(30) NOT NULL DEFAULT 'unknown',
    consent_at DATETIME NULL,
    consent_source VARCHAR(80) NULL,
    do_not_call BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_user_id INT NULL,
    deleted_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_customer_language (language),
    INDEX idx_customer_status (organization_id,customer_status),
    INDEX idx_customer_phone_tenant (organization_id,phone),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_user_id) REFERENCES app_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. conversations table
-- Stores the real-time turn-taking chat history for each customer.
CREATE TABLE IF NOT EXISTS conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    call_sid VARCHAR(255) NULL,
    event_id VARCHAR(255) NULL,
    speaker VARCHAR(20) NOT NULL, -- 'user' or 'assistant'
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_conversations_event_id (event_id),
    INDEX idx_conversations_call_turns (call_sid, id),
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

UPDATE conversations SET speaker = 'user' WHERE speaker = 'customer';

-- Safe migration for an existing database (MySQL 8.0 compatible stored block).
SET @db_name = DATABASE();
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='conversations' AND COLUMN_NAME='call_sid')=0,
  'ALTER TABLE conversations ADD COLUMN call_sid VARCHAR(255) NULL AFTER customer_id', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='conversations' AND COLUMN_NAME='event_id')=0,
  'ALTER TABLE conversations ADD COLUMN event_id VARCHAR(255) NULL AFTER call_sid', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='conversations' AND INDEX_NAME='uq_conversations_event_id')=0,
  'ALTER TABLE conversations ADD UNIQUE KEY uq_conversations_event_id (event_id)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='conversations' AND INDEX_NAME='idx_conversations_call_turns')=0,
  'ALTER TABLE conversations ADD INDEX idx_conversations_call_turns (call_sid, id)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 4. call_logs table
-- Stores call session details, durations, outcomes, transcript logs, and sheet mappings.
CREATE TABLE IF NOT EXISTS call_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    campaign_id INT NOT NULL,
    organization_id INT NOT NULL DEFAULT 1,
    call_sid VARCHAR(255) UNIQUE, -- historical provider-ID compatibility alias
    provider VARCHAR(32) NOT NULL DEFAULT 'plivo',
    provider_request_id VARCHAR(255) NULL,
    provider_call_id VARCHAR(255) NULL,
    provider_stream_id VARCHAR(255) NULL,
    provider_recording_id VARCHAR(255) NULL,
    provider_status VARCHAR(64) NULL,
    stream_status VARCHAR(64) NULL,
    correlation_id VARCHAR(64) NULL,
    provider_metadata LONGTEXT NULL,
    status VARCHAR(50) NOT NULL,
    call_status VARCHAR(50) NULL,
    lead_score INT NULL,
    lead_status VARCHAR(50) NULL,
    qualification VARCHAR(20) NULL DEFAULT 'unqualified',
    duration INT DEFAULT 0,
    stream_sid VARCHAR(255) NULL,
    call_direction VARCHAR(20) NOT NULL DEFAULT 'outbound',
    language VARCHAR(20) NOT NULL DEFAULT 'english',
    transcript LONGTEXT NULL,
    summary LONGTEXT NULL, -- Complete 3-4 line call summary: need, discussion, outcome, next action
    quick_summary VARCHAR(500) NULL, -- Short outcome used only in compact call-history lists
    stt_confidence_avg FLOAT NULL,
    tts_provider VARCHAR(40) DEFAULT 'openai',
    stt_provider VARCHAR(40) NULL,
    llm_provider VARCHAR(40) NULL,
    voice_provider VARCHAR(40) NULL,
    realtime_model VARCHAR(100) NULL,
    transcription_model VARCHAR(100) NULL,
    realtime_voice VARCHAR(100) NULL,
    voice_style_profile VARCHAR(80) NULL,
    knowledge_profile VARCHAR(80) NULL,
    conversation_profile VARCHAR(80) NULL, -- exact active conversation-policy version
    turn_gate_profile VARCHAR(80) NULL,
    first_response_latency_ms INT NULL,
    avg_response_latency_ms INT NULL,
    maximum_response_latency_ms INT NULL,
    total_turns INT NOT NULL DEFAULT 0,
    interruption_count INT NOT NULL DEFAULT 0,
    false_turn_count INT NOT NULL DEFAULT 0,
    user_speech_seconds DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    assistant_speech_seconds DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    input_audio_tokens INT NOT NULL DEFAULT 0,
    output_audio_tokens INT NOT NULL DEFAULT 0,
    input_text_tokens INT NOT NULL DEFAULT 0,
    output_text_tokens INT NOT NULL DEFAULT 0,
    estimated_openai_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    estimated_twilio_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000, -- historical
    estimated_telephony_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    provider_bill_duration_seconds INT NOT NULL DEFAULT 0,
    call_path VARCHAR(40) NULL DEFAULT 'openai_realtime',
    sheet_url VARCHAR(500) NULL,
    sheet_row INT NULL,
    outcome VARCHAR(100) NULL,
    failure_reason TEXT NULL,
    conversation_end_reason VARCHAR(80) NULL, -- customer_goodbye, provider_hangup, inactivity, etc.
    recording_url_encrypted LONGTEXT NULL,
    recording_sid VARCHAR(255) NULL,
    recording_status VARCHAR(40) NULL,
    recording_duration_seconds INT NOT NULL DEFAULT 0, -- Full provider recording duration, not call duration
    recording_channels INT NOT NULL DEFAULT 2,
    recording_retention_until DATETIME NULL,
    consent_verified BOOLEAN NOT NULL DEFAULT FALSE,
    followup_required BOOLEAN NOT NULL DEFAULT FALSE, -- set by validated English/Tamil callback intent
    followup_date DATE NULL,
    joining_date DATE NULL,
    reminder_consent VARCHAR(30) NOT NULL DEFAULT 'not_asked',
    reminder_call_date DATE NULL,
    started_at TIMESTAMP NULL,
    answered_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE
    ,FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
    ,INDEX idx_call_tenant_created (organization_id,created_at)
    ,UNIQUE INDEX uq_call_provider_id (provider,provider_call_id)
    ,UNIQUE INDEX uq_call_correlation (correlation_id)
    ,INDEX idx_call_provider_request (provider,provider_request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Safe migration for deployments created before interruption observability.
SET @db_name = DATABASE();
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='transcription_model')=0,
  'ALTER TABLE call_logs ADD COLUMN transcription_model VARCHAR(100) NULL AFTER realtime_model', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='interruption_count')=0,
  'ALTER TABLE call_logs ADD COLUMN interruption_count INT NOT NULL DEFAULT 0 AFTER total_turns', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Provider-neutral Plivo migration for existing deployments. Historical Twilio
-- identifiers and costs remain readable; they are backfilled into neutral data.
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider')=0,
  'ALTER TABLE call_logs ADD COLUMN provider VARCHAR(32) NOT NULL DEFAULT ''plivo'' AFTER call_sid', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider_request_id')=0,
  'ALTER TABLE call_logs ADD COLUMN provider_request_id VARCHAR(255) NULL AFTER provider', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider_call_id')=0,
  'ALTER TABLE call_logs ADD COLUMN provider_call_id VARCHAR(255) NULL AFTER provider_request_id', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider_stream_id')=0,
  'ALTER TABLE call_logs ADD COLUMN provider_stream_id VARCHAR(255) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider_recording_id')=0,
  'ALTER TABLE call_logs ADD COLUMN provider_recording_id VARCHAR(255) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider_status')=0,
  'ALTER TABLE call_logs ADD COLUMN provider_status VARCHAR(64) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='stream_status')=0,
  'ALTER TABLE call_logs ADD COLUMN stream_status VARCHAR(64) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='correlation_id')=0,
  'ALTER TABLE call_logs ADD COLUMN correlation_id VARCHAR(64) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider_metadata')=0,
  'ALTER TABLE call_logs ADD COLUMN provider_metadata LONGTEXT NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='estimated_telephony_cost_usd')=0,
  'ALTER TABLE call_logs ADD COLUMN estimated_telephony_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='provider_bill_duration_seconds')=0,
  'ALTER TABLE call_logs ADD COLUMN provider_bill_duration_seconds INT NOT NULL DEFAULT 0', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
UPDATE call_logs SET provider='twilio', provider_call_id=call_sid,
  provider_stream_id=stream_sid, provider_recording_id=recording_sid,
  estimated_telephony_cost_usd=estimated_twilio_cost_usd
WHERE (provider IS NULL OR provider='' OR provider='plivo')
  AND (call_sid LIKE 'CA%' OR estimated_twilio_cost_usd > 0);
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='quick_summary')=0,
  'ALTER TABLE call_logs ADD COLUMN quick_summary VARCHAR(500) NULL AFTER summary', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF(COALESCE((SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='quick_summary'),0) < 500,
  'ALTER TABLE call_logs MODIFY COLUMN quick_summary VARCHAR(500) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='call_logs' AND COLUMN_NAME='conversation_end_reason')=0,
  'ALTER TABLE call_logs ADD COLUMN conversation_end_reason VARCHAR(80) NULL AFTER failure_reason', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5. customer_memory table
-- v5 sync note: app/database/db.py init_db() auto-migrates legacy
-- customer_memory tables by adding name, intent, previous_questions,
-- lead_status, summary, updated_at, and created_at if they are missing.
-- If a legacy memory_summary column exists, init_db() makes it nullable.
-- Structured, continuously-updated memory per customer (NOT per call), used
-- to give the assistant continuity across multiple calls with the same
-- customer: who they are, what they want, what's already been asked, and
-- their current lead qualification. One row per customer (upserted).
CREATE TABLE IF NOT EXISTS customer_memory (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL UNIQUE,
    name VARCHAR(100) NULL, -- Confirmed name (may differ from the CRM record)
    intent TEXT NULL, -- What the customer is trying to do/learn/buy
    previous_questions TEXT NULL, -- JSON array of distinct questions asked across all calls
    lead_status VARCHAR(50) NULL, -- Latest qualification tier: hot, warm, cold, unqualified
    summary TEXT NULL, -- Running summary of the relationship so far
    preferred_language VARCHAR(20) NULL,
    total_calls INT NOT NULL DEFAULT 0,
    successful_calls INT NOT NULL DEFAULT 0,
    last_contacted_at TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. lead_qualifications table
-- Structured lead-extraction fields per call (name/phone/company/requirement/
-- budget/timeline), produced by app/services/lead_extraction_service.py.
-- lead_score and qualification are copied from call_logs, the canonical
-- post-call analysis result; the extraction pass does not rescore the lead.
-- Separate from call_logs.lead_score/lead_status (which are the simpler,
-- always-on call-outcome classification) — this table holds the richer
-- structured fields used for B2B-style lead qualification.
CREATE TABLE IF NOT EXISTS lead_qualifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    call_log_id INT NOT NULL,
    customer_id INT NOT NULL,
    extracted_name VARCHAR(100) NULL,
    extracted_phone VARCHAR(50) NULL,
    company VARCHAR(255) NULL,
    requirement TEXT NULL,
    budget VARCHAR(100) NULL,
    timeline VARCHAR(100) NULL,
    lead_score INT DEFAULT 0,
    qualification VARCHAR(20) DEFAULT 'unqualified', -- hot, warm, cold, unqualified
    confidence_score DECIMAL(6,5) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (call_log_id) REFERENCES call_logs (id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Raw provider and telephony events for debugging and auditing.
CREATE TABLE IF NOT EXISTS call_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    call_log_id INT NOT NULL,
    call_sid VARCHAR(255) NULL,
    event_type VARCHAR(100) NOT NULL,
    event_source VARCHAR(50) NOT NULL,
    event_data LONGTEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
    INDEX idx_event_call (call_log_id),
    INDEX idx_event_type (event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS provider_callback_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_key VARCHAR(255) NOT NULL,
    call_log_id INT NULL,
    payload LONGTEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_provider_callback (provider,event_type,event_key),
    INDEX idx_provider_callback_call (call_log_id),
    FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. Token and cost usage received from Realtime response events.
CREATE TABLE IF NOT EXISTS realtime_usage (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    call_log_id INT NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    voice_name VARCHAR(100) NULL,
    input_audio_tokens INT NOT NULL DEFAULT 0,
    output_audio_tokens INT NOT NULL DEFAULT 0,
    input_text_tokens INT NOT NULL DEFAULT 0,
    output_text_tokens INT NOT NULL DEFAULT 0,
    cached_input_audio_tokens INT NOT NULL DEFAULT 0,
    cached_input_text_tokens INT NOT NULL DEFAULT 0,
    user_speech_seconds DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    assistant_speech_seconds DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    estimated_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
    usage_data LONGTEXT NULL, -- tokens plus prompt counts, latest intent, interruption and short-response metrics; never full prompts
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
    INDEX idx_usage_call (call_log_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Existing installations may predate cached-token observability.
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='realtime_usage' AND COLUMN_NAME='cached_input_audio_tokens')=0,
  'ALTER TABLE realtime_usage ADD COLUMN cached_input_audio_tokens INT NOT NULL DEFAULT 0', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='realtime_usage' AND COLUMN_NAME='cached_input_text_tokens')=0,
  'ALTER TABLE realtime_usage ADD COLUMN cached_input_text_tokens INT NOT NULL DEFAULT 0', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 9. Scheduled callbacks and reminder calls.
CREATE TABLE IF NOT EXISTS followup_reminders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    customer_id INT NOT NULL,
    campaign_id INT NULL,
    source_call_log_id INT NULL,
    reminder_type VARCHAR(50) NOT NULL DEFAULT 'callback',
    source VARCHAR(40) NOT NULL DEFAULT 'post_call_analysis',
    requested_date DATE NULL,
    scheduled_at DATETIME NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    assigned_user_id INT NULL,
    notes TEXT NULL,
    completed_at DATETIME NULL,
    completed_by_user_id INT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
    FOREIGN KEY (source_call_log_id) REFERENCES call_logs(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_user_id) REFERENCES app_users(id) ON DELETE SET NULL,
    FOREIGN KEY (completed_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL,
    UNIQUE KEY uq_followup_idempotency (idempotency_key),
    INDEX idx_reminder_tenant_status_due (organization_id, status, scheduled_at),
    INDEX idx_reminder_assignee_status (organization_id, assigned_user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Durable tenant CRM configuration. Secrets remain encrypted in api_credentials.
CREATE TABLE IF NOT EXISTS crm_connections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    provider VARCHAR(50) NOT NULL DEFAULT 'webhook',
    name VARCHAR(120) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    field_mapping_json JSON NULL,
    last_tested_at DATETIME NULL,
    last_test_status VARCHAR(30) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_crm_connection_provider (organization_id,provider),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS crm_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    connection_id INT NULL,
    event_type VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(191) NOT NULL,
    payload_json JSON NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 8,
    available_at DATETIME NOT NULL,
    locked_at DATETIME NULL,
    locked_by VARCHAR(191) NULL,
    last_error VARCHAR(1000) NULL,
    response_status INT NULL,
    delivered_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_crm_outbox_idempotency (organization_id,idempotency_key),
    INDEX idx_crm_outbox_claim (status,available_at,id),
    INDEX idx_crm_outbox_tenant (organization_id,status,created_at),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (connection_id) REFERENCES crm_connections(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Operator-controlled human handoff destinations, departments, and state history.
CREATE TABLE IF NOT EXISTS departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    name VARCHAR(80) NOT NULL,
    description VARCHAR(255) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_department_name (organization_id,name),
    INDEX idx_department_active (organization_id,is_active),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS staff_destinations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    name VARCHAR(120) NOT NULL,
    phone_e164 VARCHAR(16) NOT NULL,
    department VARCHAR(80) NULL,
    priority INT NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_staff_destination_phone (organization_id,phone_e164),
    INDEX idx_staff_destination_active (organization_id,is_active,priority),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS call_transfers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    call_log_id INT NOT NULL,
    destination_id INT NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'requested',
    provider_call_id VARCHAR(255) NOT NULL,
    provider_bleg_id VARCHAR(255) NULL,
    initiated_by_user_id INT NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    failure_reason VARCHAR(500) NULL,
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    answered_at DATETIME NULL,
    completed_at DATETIME NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_call_transfer_idempotency (organization_id,idempotency_key),
    INDEX idx_call_transfer_call (organization_id,call_log_id,requested_at),
    INDEX idx_call_transfer_status (organization_id,status,requested_at),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
    FOREIGN KEY (destination_id) REFERENCES staff_destinations(id),
    FOREIGN KEY (initiated_by_user_id) REFERENCES app_users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Per-organization IVR menu. Disabled by default; it runs after the existing
-- English/Tamil selector and routes a caller into a tenant-owned campaign.
CREATE TABLE IF NOT EXISTS organization_ivr_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    timeout_seconds TINYINT NOT NULL DEFAULT 7,
    prompt_english VARCHAR(500) NOT NULL DEFAULT '',
    prompt_tamil VARCHAR(500) NOT NULL DEFAULT '',
    audio_token VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ivr_settings_organization (organization_id),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS organization_ivr_options (
    id INT AUTO_INCREMENT PRIMARY KEY,
    settings_id INT NOT NULL,
    digit CHAR(1) NOT NULL,
    label VARCHAR(80) NOT NULL,
    campaign_id INT NULL,
    destination_id INT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 100,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ivr_option_digit (settings_id,digit),
    INDEX idx_ivr_option_active (settings_id,is_active,sort_order),
    FOREIGN KEY (settings_id) REFERENCES organization_ivr_settings(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE RESTRICT,
    FOREIGN KEY (destination_id) REFERENCES staff_destinations(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS call_ivr_selections (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    call_log_id INT NOT NULL,
    menu_option_id INT NOT NULL,
    digit CHAR(1) NOT NULL,
    label VARCHAR(80) NOT NULL,
    campaign_id INT NULL,
    destination_id INT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_call_ivr_selection (call_log_id),
    INDEX idx_call_ivr_org_created (organization_id,created_at),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
    FOREIGN KEY (menu_option_id) REFERENCES organization_ivr_options(id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
    FOREIGN KEY (destination_id) REFERENCES staff_destinations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Worker liveness is operational metadata only; it contains no tenant data.
CREATE TABLE IF NOT EXISTS runtime_worker_heartbeats (
    worker_name VARCHAR(80) PRIMARY KEY,
    worker_id VARCHAR(191) NOT NULL,
    last_seen_at DATETIME NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_runtime_heartbeat_seen (last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. Optional document metadata. Vector embeddings remain in ChromaDB.
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NULL,
    file_name VARCHAR(255) NULL,
    file_path VARCHAR(500) NULL,
    content LONGTEXT NULL,
    language VARCHAR(20) NOT NULL DEFAULT 'english',
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_knowledge_language (language),
    INDEX idx_knowledge_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. Non-secret runtime defaults. API keys must stay in .env.
CREATE TABLE IF NOT EXISTS system_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value LONGTEXT NULL,
    is_secret BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Security audit trail. Never store passwords, tokens, raw API keys or full
-- transcript content in this table.
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    actor_user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(80) NULL,
    resource_id VARCHAR(100) NULL,
    request_id VARCHAR(64) NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500) NULL,
    result VARCHAR(30) NOT NULL DEFAULT 'success',
    metadata_json JSON NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (actor_user_id) REFERENCES app_users(id) ON DELETE SET NULL,
    INDEX idx_audit_tenant_created (organization_id,created_at),
    INDEX idx_audit_action (organization_id,action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS api_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    provider VARCHAR(50) NOT NULL,
    credential_ciphertext LONGTEXT NOT NULL,
    key_version VARCHAR(50) NOT NULL,
    last_four VARCHAR(8) NULL,
    rotated_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_tenant_provider (organization_id,provider),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
    INDEX idx_session_expiry (user_id,expires_at,revoked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS suppression_list (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    phone_hash CHAR(64) NOT NULL,
    reason VARCHAR(100) NOT NULL DEFAULT 'customer_opt_out',
    source VARCHAR(80) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_suppression_tenant_phone (organization_id,phone_hash),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO system_settings (setting_key, setting_value, is_secret) VALUES
    ('twilio_voice_engine', 'openai_realtime', FALSE),
    ('openai_realtime_model', 'gpt-realtime-2.1-mini', FALSE),
    ('openai_realtime_model_tamil', 'gpt-realtime-2.1', FALSE),
    ('openai_transcription_model', 'gpt-4o-mini-transcribe', FALSE),
    ('openai_transcription_model_tamil', 'gpt-4o-transcribe', FALSE),
    ('openai_transcription_language_tamil', '', FALSE),
    ('openai_realtime_voice', 'marin', FALSE), -- legacy compatibility only
    ('openai_realtime_voice_english', 'shimmer', FALSE),
    ('openai_realtime_voice_tamil', 'marin', FALSE),
    ('tamil_voice_style_profile', 'natural_tamil_tn_query_first_v7', FALSE),
    ('tamil_knowledge_profile', 'tamil_semantic_parity_v2', FALSE),
    ('sales_conversation_profile', 'consultative_education_sales_v2', FALSE),
    ('tamil_turn_gate_profile', 'tamil_fast_semantic_barge_in_v4', FALSE),
    ('tamil_barge_in_confirm_ms', '80', FALSE),
    ('tamil_barge_in_min_voiced_frames', '2', FALSE),
    ('openai_vad_eagerness_tamil', 'medium', FALSE),
    ('tamil_core_knowledge_max_chars', '4200', FALSE),
    ('default_language', 'english', FALSE)
ON DUPLICATE KEY UPDATE
    setting_value = VALUES(setting_value),
    is_secret = VALUES(is_secret);

-- Nectar Facility Operations foundation. Facility records are tenant-scoped
-- through facility_sites.organization_id and are separate from sales data.
CREATE TABLE IF NOT EXISTS facility_sites (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    name VARCHAR(180) NOT NULL,
    code VARCHAR(80) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_facility_site_code (organization_id, code),
    INDEX idx_facility_site_org (organization_id),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS facility_assets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    site_id BIGINT NOT NULL,
    asset_code VARCHAR(100) NOT NULL,
    name VARCHAR(180) NOT NULL,
    asset_type VARCHAR(80) NOT NULL,
    status ENUM('operational','degraded','offline','maintenance') NOT NULL DEFAULT 'operational',
    location VARCHAR(180) NULL,
    metadata_json JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_facility_asset_code (site_id, asset_code),
    INDEX idx_facility_asset_site_status (site_id, status),
    FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS facility_sensor_readings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    site_id BIGINT NOT NULL,
    asset_id BIGINT NULL,
    sensor_code VARCHAR(100) NOT NULL,
    metric VARCHAR(80) NOT NULL,
    value DECIMAL(14,4) NOT NULL,
    unit VARCHAR(32) NOT NULL,
    observed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_facility_sensor_site_observed (site_id, observed_at),
    INDEX idx_facility_sensor_asset_metric (asset_id, metric, observed_at),
    FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS facility_alerts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    site_id BIGINT NOT NULL,
    asset_id BIGINT NULL,
    severity ENUM('critical','high','medium','low') NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status ENUM('active','acknowledged','resolved') NOT NULL DEFAULT 'active',
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,
    INDEX idx_facility_alert_site_status (site_id, status, severity),
    FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS facility_service_requests (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    site_id BIGINT NOT NULL,
    asset_id BIGINT NULL,
    request_number VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    priority ENUM('critical','high','medium','low') NOT NULL DEFAULT 'medium',
    status ENUM('open','in_progress','resolved','cancelled') NOT NULL DEFAULT 'open',
    requested_by_user_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_facility_request_site_status (site_id, status),
    FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS facility_asset_relationships (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    from_asset_id BIGINT NOT NULL,
    to_asset_id BIGINT NOT NULL,
    relationship_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_facility_asset_relationship (from_asset_id, to_asset_id, relationship_type),
    INDEX idx_facility_relationship_to (to_asset_id),
    FOREIGN KEY (from_asset_id) REFERENCES facility_assets(id) ON DELETE CASCADE,
    FOREIGN KEY (to_asset_id) REFERENCES facility_assets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS facility_action_confirmations (
    id CHAR(36) PRIMARY KEY,
    organization_id INT NOT NULL,
    requested_by_user_id INT NOT NULL,
    action_type VARCHAR(80) NOT NULL,
    payload_json JSON NOT NULL,
    status ENUM('pending','approved','consumed','expired','rejected') NOT NULL DEFAULT 'pending',
    expires_at DATETIME NOT NULL,
    consumed_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_facility_confirmation_lookup (organization_id, requested_by_user_id, status, expires_at),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
