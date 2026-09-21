import os
import re
import pymysql
import pymysql.cursors
from typing import Generator
from dotenv import load_dotenv

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), override=True)

# Load database configuration from environment
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "digidara_voice_ai")
if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
    raise RuntimeError("DB_NAME may contain only letters, numbers, and underscores")

def init_db():
    """Initializes the MySQL database and creates tables if they do not exist."""
    # Connect without a database name to create the database if it doesn't exist
    conn = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    conn.commit()
    conn.close()

    # Connect to the created database to define tables
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(180) NOT NULL,
            slug VARCHAR(100) NOT NULL UNIQUE, status VARCHAR(30) NOT NULL DEFAULT 'active',
            plan_code VARCHAR(50) NOT NULL DEFAULT 'professional',
            monthly_call_limit INT NOT NULL DEFAULT 10000,
            data_retention_days INT NOT NULL DEFAULT 90,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""INSERT INTO organizations (id,name,slug) VALUES
        (1,'DigiDara Technologies','digidara') ON DUPLICATE KEY UPDATE name=VALUES(name)""")
    cursor.execute("SHOW COLUMNS FROM organizations")
    org_columns = [col["Field"] for col in cursor.fetchall()]
    if "timezone" not in org_columns:
        cursor.execute(
            "ALTER TABLE organizations ADD COLUMN timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata'"
        )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_users (
            id INT AUTO_INCREMENT PRIMARY KEY, organization_id INT NOT NULL,
            email VARCHAR(190) NOT NULL, password_hash VARCHAR(255) NULL,
            full_name VARCHAR(150) NOT NULL, role_code VARCHAR(30) NOT NULL DEFAULT 'agent',
            is_active BOOLEAN NOT NULL DEFAULT TRUE, mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            failed_login_attempts INT NOT NULL DEFAULT 0, locked_until DATETIME NULL,
            last_login_at DATETIME NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_user_tenant_email (organization_id,email)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assistant_chat_messages (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL DEFAULT 1,
            user_id INT NOT NULL,
            role VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            page_path VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_assistant_chat_user_created (user_id,created_at)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL,
            phone VARCHAR(20),
            language VARCHAR(50) NULL,
            investigated_course VARCHAR(255) NULL,
            internship_or_course VARCHAR(100) NULL,
            course_duration VARCHAR(100) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_customer_tenant_email (organization_id,email)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            campaign_name VARCHAR(255) NOT NULL,
            objective TEXT NOT NULL,
            ai_prompt TEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            customer_id INT NOT NULL,
            call_sid VARCHAR(255) NULL,
            event_id VARCHAR(255) NULL UNIQUE,
            speaker VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS call_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            customer_id INT NOT NULL,
            campaign_id INT NOT NULL,
            organization_id INT NOT NULL,
            call_sid VARCHAR(255),
            status VARCHAR(50) NOT NULL,
                duration INT DEFAULT 0,
                transcript TEXT NULL,
                summary TEXT NULL,
                stt_confidence_avg FLOAT NULL,
                tts_provider VARCHAR(40) DEFAULT 'openai',
                stt_provider VARCHAR(40) NULL,
                llm_provider VARCHAR(40) NULL,
                voice_provider VARCHAR(40) NULL,
                realtime_model VARCHAR(100) NULL,
                transcription_model VARCHAR(100) NULL,
                avg_response_latency_ms INT NULL,
            sheet_url VARCHAR(500) NULL,
            sheet_row INT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_memory (
            id INT AUTO_INCREMENT PRIMARY KEY,
            customer_id INT NOT NULL UNIQUE,
            name VARCHAR(100) NULL,
            intent TEXT NULL,
            previous_questions TEXT NULL,
            lead_status VARCHAR(50) NULL,
            summary TEXT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
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
            qualification VARCHAR(20) DEFAULT 'unqualified',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (call_log_id) REFERENCES call_logs (id) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
        )
    """)
    
    # Check and add columns in case the table already existed without them
    cursor.execute("SHOW COLUMNS FROM customers")
    cust_columns = [col["Field"] for col in cursor.fetchall()]
    if "organization_id" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN organization_id INT NOT NULL DEFAULT 1")
    cursor.execute("SHOW INDEX FROM customers")
    customer_indexes = cursor.fetchall()
    email_only_unique_indexes = {
        row["Key_name"] for row in customer_indexes
        if not row["Non_unique"] and row["Column_name"] == "email"
        and sum(1 for item in customer_indexes if item["Key_name"] == row["Key_name"]) == 1
    }
    for index_name in email_only_unique_indexes:
        if not re.fullmatch(r"[A-Za-z0-9_]+", index_name):
            raise RuntimeError("Unsafe customer index name")
        cursor.execute(f"ALTER TABLE customers DROP INDEX `{index_name}`")
    cursor.execute("SHOW INDEX FROM customers WHERE Key_name='uq_customer_tenant_email'")
    if not cursor.fetchone():
        cursor.execute(
            "CREATE UNIQUE INDEX uq_customer_tenant_email "
            "ON customers(organization_id,email)"
        )
    if "consent_status" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN consent_status VARCHAR(30) NOT NULL DEFAULT 'unknown'")
    if "consent_at" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN consent_at DATETIME NULL")
    if "do_not_call" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN do_not_call BOOLEAN NOT NULL DEFAULT FALSE")
    if "deleted_at" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN deleted_at DATETIME NULL")
    if "language" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN language VARCHAR(50) NULL")
    if "investigated_course" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN investigated_course VARCHAR(255) NULL")
    if "internship_or_course" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN internship_or_course VARCHAR(100) NULL")
    if "course_duration" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN course_duration VARCHAR(100) NULL")
    if "customer_status" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN customer_status VARCHAR(50) NOT NULL DEFAULT 'new'")
    if "is_active" not in cust_columns:
        cursor.execute("ALTER TABLE customers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE")
    cursor.execute("SHOW INDEX FROM customers WHERE Key_name='idx_customer_status'")
    if not cursor.fetchone():
        cursor.execute(
            "CREATE INDEX idx_customer_status ON customers(organization_id,customer_status)"
        )

    cursor.execute("SHOW COLUMNS FROM campaigns")
    campaign_columns = [col["Field"] for col in cursor.fetchall()]
    if "organization_id" not in campaign_columns:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN organization_id INT NOT NULL DEFAULT 1")
    if "status" not in campaign_columns:
        cursor.execute(
            "ALTER TABLE campaigns ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'active'"
        )
    cursor.execute("SHOW INDEX FROM campaigns WHERE Key_name='idx_campaign_status'")
    if not cursor.fetchone():
        cursor.execute(
            "CREATE INDEX idx_campaign_status ON campaigns(organization_id,status)"
        )

    cursor.execute("SHOW COLUMNS FROM call_logs")
    columns = [col["Field"] for col in cursor.fetchall()]
    if "organization_id" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN organization_id INT NOT NULL DEFAULT 1")
    if "consent_verified" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN consent_verified BOOLEAN NOT NULL DEFAULT FALSE")
    if "recording_retention_until" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN recording_retention_until DATETIME NULL")
    if "campaign_id" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN campaign_id INT NULL")
    if "status" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN status VARCHAR(50) NULL")
    if "call_status" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN call_status VARCHAR(50) NULL")
    if "lead_score" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN lead_score INT NULL")
    if "lead_status" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN lead_status VARCHAR(50) NULL")
    if "qualification" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN qualification VARCHAR(20) NULL DEFAULT 'unqualified'")
    if "quick_summary" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN quick_summary VARCHAR(500) NULL")
    else:
        cursor.execute("SHOW COLUMNS FROM call_logs LIKE 'quick_summary'")
        quick_summary_column = cursor.fetchone() or {}
        quick_summary_type = str(
            quick_summary_column.get("Type")
            or quick_summary_column.get("type")
            or ""
        ).lower()
        if quick_summary_type and "varchar(500)" not in quick_summary_type:
            cursor.execute("ALTER TABLE call_logs MODIFY COLUMN quick_summary VARCHAR(500) NULL")
    if "call_path" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN call_path VARCHAR(20) NULL DEFAULT 'gather'")
    if "duration" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN duration INT DEFAULT 0")
    if "transcript" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN transcript TEXT NULL")
    if "summary" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN summary TEXT NULL")
    if "stt_confidence_avg" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN stt_confidence_avg FLOAT NULL")
    if "tts_provider" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN tts_provider VARCHAR(40) DEFAULT 'openai'")
    if "stt_provider" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN stt_provider VARCHAR(40) NULL")
    if "llm_provider" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN llm_provider VARCHAR(40) NULL")
    if "voice_provider" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN voice_provider VARCHAR(40) NULL")
    if "realtime_model" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN realtime_model VARCHAR(100) NULL")
    if "transcription_model" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN transcription_model VARCHAR(100) NULL")
    if "avg_response_latency_ms" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN avg_response_latency_ms INT NULL")
    if "first_response_latency_ms" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN first_response_latency_ms INT NULL")
    if "maximum_response_latency_ms" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN maximum_response_latency_ms INT NULL")
    if "language" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN language VARCHAR(20) NOT NULL DEFAULT 'english'")
    if "realtime_voice" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN realtime_voice VARCHAR(100) NULL")
    else:
        # Custom OpenAI voice IDs can be longer than built-in voice names.
        cursor.execute("SHOW COLUMNS FROM call_logs LIKE 'realtime_voice'")
        realtime_voice_column = cursor.fetchone() or {}
        realtime_voice_type = str(
            realtime_voice_column.get("Type")
            or realtime_voice_column.get("type")
            or ""
        ).lower()
        if realtime_voice_type and "varchar(100)" not in realtime_voice_type:
            cursor.execute("ALTER TABLE call_logs MODIFY COLUMN realtime_voice VARCHAR(100) NULL")
    if "voice_style_profile" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN voice_style_profile VARCHAR(80) NULL")
    if "knowledge_profile" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN knowledge_profile VARCHAR(80) NULL")
    if "conversation_profile" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN conversation_profile VARCHAR(80) NULL")
    if "conversation_end_reason" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN conversation_end_reason VARCHAR(80) NULL")
    if "turn_gate_profile" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN turn_gate_profile VARCHAR(80) NULL")
    if "estimated_openai_cost_usd" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN estimated_openai_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0")
    if "estimated_twilio_cost_usd" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN estimated_twilio_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0")
    if "stream_sid" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN stream_sid VARCHAR(255) NULL")
        columns.append("stream_sid")
    if "recording_sid" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN recording_sid VARCHAR(255) NULL")
        columns.append("recording_sid")
    for name, definition in {
        "provider": "VARCHAR(32) NOT NULL DEFAULT 'plivo'",
        "provider_request_id": "VARCHAR(255) NULL",
        "provider_call_id": "VARCHAR(255) NULL",
        "provider_stream_id": "VARCHAR(255) NULL",
        "provider_recording_id": "VARCHAR(255) NULL",
        "provider_status": "VARCHAR(64) NULL",
        "stream_status": "VARCHAR(64) NULL",
        "correlation_id": "VARCHAR(64) NULL",
        "provider_metadata": "LONGTEXT NULL",
        "estimated_telephony_cost_usd": "DECIMAL(12,6) NOT NULL DEFAULT 0",
        "provider_bill_duration_seconds": "INT NOT NULL DEFAULT 0",
    }.items():
        if name not in columns:
            cursor.execute(f"ALTER TABLE call_logs ADD COLUMN {name} {definition}")
    cursor.execute("""UPDATE call_logs SET provider='twilio',provider_call_id=call_sid,
        provider_stream_id=stream_sid,provider_recording_id=recording_sid,
        estimated_telephony_cost_usd=estimated_twilio_cost_usd
        WHERE (provider IS NULL OR provider='' OR provider='plivo')
          AND (call_sid LIKE 'CA%' OR estimated_twilio_cost_usd > 0)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS provider_callback_events (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        provider VARCHAR(32) NOT NULL,event_type VARCHAR(100) NOT NULL,
        event_key VARCHAR(255) NOT NULL,call_log_id INT NULL,payload LONGTEXT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_provider_callback (provider,event_type,event_key),
        INDEX idx_provider_callback_call (call_log_id),
        FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")
    cursor.execute("SHOW INDEX FROM call_logs WHERE Key_name='uq_call_provider_id'")
    if not cursor.fetchone():
        cursor.execute(
            "CREATE UNIQUE INDEX uq_call_provider_id ON call_logs(provider,provider_call_id)"
        )
    cursor.execute("SHOW INDEX FROM call_logs WHERE Key_name='uq_call_correlation'")
    if not cursor.fetchone():
        cursor.execute(
            "CREATE UNIQUE INDEX uq_call_correlation ON call_logs(correlation_id)"
        )
    cursor.execute("SHOW INDEX FROM call_logs WHERE Key_name='idx_call_provider_request'")
    if not cursor.fetchone():
        cursor.execute(
            "CREATE INDEX idx_call_provider_request ON call_logs(provider,provider_request_id)"
        )
    if "failure_reason" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN failure_reason TEXT NULL")
    if "outcome" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN outcome VARCHAR(100) NULL")
    if "sheet_url" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN sheet_url VARCHAR(500) NULL")
    if "sheet_row" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN sheet_row INT NULL")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE call_logs ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    for name, definition in {
        "input_audio_tokens": "INT NOT NULL DEFAULT 0",
        "output_audio_tokens": "INT NOT NULL DEFAULT 0",
        "input_text_tokens": "INT NOT NULL DEFAULT 0",
        "output_text_tokens": "INT NOT NULL DEFAULT 0",
        "total_turns": "INT NOT NULL DEFAULT 0",
        "interruption_count": "INT NOT NULL DEFAULT 0",
        "false_turn_count": "INT NOT NULL DEFAULT 0",
        "recording_sid": "VARCHAR(255) NULL",
        "recording_status": "VARCHAR(40) NULL",
        "recording_duration_seconds": "INT NOT NULL DEFAULT 0",
        "recording_channels": "INT NOT NULL DEFAULT 2",
        "started_at": "TIMESTAMP NULL",
        "answered_at": "TIMESTAMP NULL",
        "completed_at": "TIMESTAMP NULL",
        "call_direction": "VARCHAR(20) NOT NULL DEFAULT 'outbound'",
        "followup_required": "BOOLEAN NOT NULL DEFAULT FALSE",
        "followup_date": "DATE NULL",
    }.items():
        if name not in columns:
            cursor.execute(f"ALTER TABLE call_logs ADD COLUMN {name} {definition}")

    # A server restart or missed provider callback must never leave a call live forever.
    cursor.execute("""UPDATE call_logs SET status='failed', call_status='failed',
        failure_reason=COALESCE(failure_reason,'Recovered stale call after missing final callback'),
        duration=GREATEST(COALESCE(duration,0), TIMESTAMPDIFF(SECOND,created_at,NOW()))
        WHERE COALESCE(call_status,status) IN ('initiated','queued','ringing','in-progress','ongoing')
          AND created_at < NOW() - INTERVAL 2 HOUR""")

    cursor.execute("SHOW COLUMNS FROM conversations")
    conversation_columns = [col["Field"] for col in cursor.fetchall()]
    if "created_at" not in conversation_columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    if "call_sid" not in conversation_columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN call_sid VARCHAR(255) NULL AFTER customer_id")
    if "event_id" not in conversation_columns:
        cursor.execute("ALTER TABLE conversations ADD COLUMN event_id VARCHAR(255) NULL AFTER call_sid")
    cursor.execute("SHOW INDEX FROM conversations WHERE Key_name = 'uq_conversations_event_id'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE conversations ADD UNIQUE INDEX uq_conversations_event_id (event_id)")
    cursor.execute("SHOW INDEX FROM conversations WHERE Key_name = 'idx_conversations_call_turns'")
    if not cursor.fetchone():
        cursor.execute("CREATE INDEX idx_conversations_call_turns ON conversations (call_sid, id)")
    cursor.execute("UPDATE conversations SET speaker = 'user' WHERE speaker = 'customer'")

    cursor.execute("SHOW COLUMNS FROM customer_memory")
    memory_columns = [col["Field"] for col in cursor.fetchall()]
    if "name" not in memory_columns:
        cursor.execute("ALTER TABLE customer_memory ADD COLUMN name VARCHAR(100) NULL")
    if "intent" not in memory_columns:
        cursor.execute("ALTER TABLE customer_memory ADD COLUMN intent TEXT NULL")
    if "previous_questions" not in memory_columns:
        cursor.execute("ALTER TABLE customer_memory ADD COLUMN previous_questions TEXT NULL")
    if "lead_status" not in memory_columns:
        cursor.execute("ALTER TABLE customer_memory ADD COLUMN lead_status VARCHAR(50) NULL")
    if "summary" not in memory_columns:
        cursor.execute("ALTER TABLE customer_memory ADD COLUMN summary TEXT NULL")
    if "memory_summary" in memory_columns:
        cursor.execute("ALTER TABLE customer_memory MODIFY COLUMN memory_summary TEXT NULL")
    if "updated_at" not in memory_columns:
        cursor.execute("ALTER TABLE customer_memory ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    if "created_at" not in memory_columns:
        cursor.execute("ALTER TABLE customer_memory ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS realtime_usage (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, call_log_id INT NOT NULL,
            model_name VARCHAR(100) NOT NULL, voice_name VARCHAR(100) NULL,
            input_audio_tokens INT NOT NULL DEFAULT 0, output_audio_tokens INT NOT NULL DEFAULT 0,
            input_text_tokens INT NOT NULL DEFAULT 0, output_text_tokens INT NOT NULL DEFAULT 0,
            cached_input_audio_tokens INT NOT NULL DEFAULT 0, cached_input_text_tokens INT NOT NULL DEFAULT 0,
            user_speech_seconds DECIMAL(10,2) NOT NULL DEFAULT 0,
            assistant_speech_seconds DECIMAL(10,2) NOT NULL DEFAULT 0,
            estimated_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0,
            usage_data LONGTEXT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
            INDEX idx_usage_call (call_log_id)
        )
    """)
    cursor.execute("SHOW COLUMNS FROM realtime_usage LIKE 'voice_name'")
    usage_voice_column = cursor.fetchone() or {}
    usage_voice_type = str(
        usage_voice_column.get("Type") or usage_voice_column.get("type") or ""
    ).lower()
    if usage_voice_type and "varchar(100)" not in usage_voice_type:
        cursor.execute("ALTER TABLE realtime_usage MODIFY COLUMN voice_name VARCHAR(100) NULL")
    cursor.execute("SHOW COLUMNS FROM realtime_usage")
    usage_columns = {column["Field"] for column in cursor.fetchall()}
    for name in ("cached_input_audio_tokens", "cached_input_text_tokens"):
        if name not in usage_columns:
            cursor.execute(
                f"ALTER TABLE realtime_usage ADD COLUMN {name} "
                "INT NOT NULL DEFAULT 0"
            )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, organization_id INT NOT NULL,
            actor_user_id INT NULL, action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(80) NULL, resource_id VARCHAR(100) NULL,
            request_id VARCHAR(64) NULL, ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(500) NULL, result VARCHAR(30) NOT NULL DEFAULT 'success',
            metadata_json JSON NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_audit_tenant_created (organization_id,created_at)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_credentials (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            provider VARCHAR(50) NOT NULL,
            credential_ciphertext LONGTEXT NOT NULL,
            key_version VARCHAR(50) NOT NULL,
            last_four VARCHAR(8) NULL,
            rotated_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_tenant_provider (organization_id,provider),
            FOREIGN KEY (organization_id) REFERENCES organizations (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL,
            refresh_token_hash CHAR(64) NOT NULL UNIQUE, expires_at DATETIME NOT NULL,
            revoked_at DATETIME NULL, ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(500) NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_session_expiry (user_id,expires_at,revoked_at)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppression_list (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, organization_id INT NOT NULL,
            phone_hash CHAR(64) NOT NULL, reason VARCHAR(100) NOT NULL DEFAULT 'customer_opt_out',
            source VARCHAR(80) NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_suppression_tenant_phone (organization_id,phone_hash)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bulk_upload_rows (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            upload_id CHAR(36) NOT NULL, organization_id INT NOT NULL, campaign_id INT NOT NULL,
            row_index INT NOT NULL, name VARCHAR(100) NULL, phone VARCHAR(30) NULL,
            language VARCHAR(20) NULL, investigated_course VARCHAR(255) NULL,
            internship_or_course VARCHAR(100) NULL, course_duration VARCHAR(100) NULL,
            status VARCHAR(30) NOT NULL DEFAULT '', source_filename VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_upload_row (upload_id,row_index),
            INDEX idx_upload_status (upload_id,status),
            INDEX idx_upload_tenant (organization_id,upload_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plivo_compliance_applications (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            plivo_compliance_id VARCHAR(64) NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            country_iso VARCHAR(5) NOT NULL DEFAULT 'IN',
            number_type VARCHAR(20) NOT NULL DEFAULT 'local',
            business_name VARCHAR(255) NULL, business_email VARCHAR(190) NULL,
            provisioned_number VARCHAR(30) NULL, subaccount_auth_id VARCHAR(64) NULL,
            raw_response LONGTEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_compliance_org (organization_id),
            INDEX idx_compliance_plivo_id (plivo_compliance_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS phone_numbers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            campaign_id INT NOT NULL,
            plivo_number VARCHAR(20) NOT NULL,
            label VARCHAR(120) NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_phone_numbers_number (plivo_number),
            INDEX idx_phone_numbers_org (organization_id),
            FOREIGN KEY (organization_id) REFERENCES organizations (id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS business_hours (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            day_of_week TINYINT NOT NULL,
            is_closed BOOLEAN NOT NULL DEFAULT FALSE,
            open_time VARCHAR(5) NULL,
            close_time VARCHAR(5) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_business_hours_org_day (organization_id, day_of_week),
            FOREIGN KEY (organization_id) REFERENCES organizations (id)
        )
    """)
    cursor.execute("""
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_followup_idempotency (idempotency_key),
            INDEX idx_reminder_tenant_status_due (organization_id,status,scheduled_at),
            INDEX idx_reminder_assignee_status (organization_id,assigned_user_id,status),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
            FOREIGN KEY (source_call_log_id) REFERENCES call_logs(id) ON DELETE SET NULL,
            FOREIGN KEY (assigned_user_id) REFERENCES app_users(id) ON DELETE SET NULL,
            FOREIGN KEY (completed_by_user_id) REFERENCES app_users(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("SHOW COLUMNS FROM followup_reminders")
    reminder_columns = {column["Field"] for column in cursor.fetchall()}
    reminder_additions = {
        "organization_id": "INT NULL AFTER id",
        "source": "VARCHAR(40) NOT NULL DEFAULT 'post_call_analysis' AFTER reminder_type",
        "requested_date": "DATE NULL AFTER source",
        "timezone": "VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata' AFTER scheduled_at",
        "assigned_user_id": "INT NULL AFTER status",
        "completed_by_user_id": "INT NULL AFTER completed_at",
        "idempotency_key": "VARCHAR(191) NULL AFTER completed_by_user_id",
    }
    for name, definition in reminder_additions.items():
        if name not in reminder_columns:
            cursor.execute(f"ALTER TABLE followup_reminders ADD COLUMN {name} {definition}")
    cursor.execute("ALTER TABLE followup_reminders MODIFY COLUMN scheduled_at DATETIME NULL")
    cursor.execute(
        """UPDATE followup_reminders fr JOIN customers c ON c.id=fr.customer_id
              SET fr.organization_id=c.organization_id
            WHERE fr.organization_id IS NULL"""
    )
    cursor.execute(
        "UPDATE followup_reminders SET idempotency_key=CONCAT('legacy:callback:',id) "
        "WHERE idempotency_key IS NULL OR idempotency_key=''"
    )
    cursor.execute("ALTER TABLE followup_reminders MODIFY COLUMN organization_id INT NOT NULL")
    cursor.execute("ALTER TABLE followup_reminders MODIFY COLUMN idempotency_key VARCHAR(191) NOT NULL")
    cursor.execute("SHOW INDEX FROM followup_reminders")
    reminder_indexes = {row["Key_name"] for row in cursor.fetchall()}
    if "uq_followup_idempotency" not in reminder_indexes:
        cursor.execute("CREATE UNIQUE INDEX uq_followup_idempotency ON followup_reminders(idempotency_key)")
    if "idx_reminder_tenant_status_due" not in reminder_indexes:
        cursor.execute(
            "CREATE INDEX idx_reminder_tenant_status_due "
            "ON followup_reminders(organization_id,status,scheduled_at)"
        )
    if "idx_reminder_assignee_status" not in reminder_indexes:
        cursor.execute(
            "CREATE INDEX idx_reminder_assignee_status "
            "ON followup_reminders(organization_id,assigned_user_id,status)"
        )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crm_connections (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            provider VARCHAR(50) NOT NULL DEFAULT 'webhook',
            name VARCHAR(120) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            field_mapping_json JSON NULL,
            last_tested_at DATETIME NULL,
            last_test_status VARCHAR(30) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_crm_connection_provider (organization_id,provider),
            INDEX idx_crm_connection_active (organization_id,is_active),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_crm_outbox_idempotency (organization_id,idempotency_key),
            INDEX idx_crm_outbox_claim (status,available_at,id),
            INDEX idx_crm_outbox_tenant (organization_id,status,created_at),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (connection_id) REFERENCES crm_connections(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            name VARCHAR(80) NOT NULL,
            description VARCHAR(255) NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_department_name (organization_id,name),
            INDEX idx_department_active (organization_id,is_active),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        INSERT IGNORE INTO departments (organization_id, name, description)
        SELECT o.id, d.name, d.description
        FROM organizations o
        CROSS JOIN (
            SELECT 'Business' AS name, 'Business operations and partnerships' AS description
            UNION ALL SELECT 'Sales', 'Direct sales and inbound inquiries'
            UNION ALL SELECT 'Education', 'Customer education and product advisory'
        ) d
    """)
    cursor.execute("""
        INSERT IGNORE INTO departments (organization_id, name)
        SELECT DISTINCT organization_id, department
        FROM staff_destinations
        WHERE department IS NOT NULL AND TRIM(department) != ''
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff_destinations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            name VARCHAR(120) NOT NULL,
            phone_e164 VARCHAR(16) NOT NULL,
            department VARCHAR(80) NULL,
            priority INT NOT NULL DEFAULT 100,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_staff_destination_phone (organization_id,phone_e164),
            INDEX idx_staff_destination_active (organization_id,is_active,priority),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
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
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            answered_at DATETIME NULL,
            completed_at DATETIME NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_call_transfer_idempotency (organization_id,idempotency_key),
            INDEX idx_call_transfer_call (organization_id,call_log_id,requested_at),
            INDEX idx_call_transfer_status (organization_id,status,requested_at),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
            FOREIGN KEY (destination_id) REFERENCES staff_destinations(id),
            FOREIGN KEY (initiated_by_user_id) REFERENCES app_users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organization_ivr_settings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            timeout_seconds TINYINT NOT NULL DEFAULT 7,
            prompt_english VARCHAR(500) NOT NULL DEFAULT '',
            prompt_tamil VARCHAR(500) NOT NULL DEFAULT '',
            audio_token VARCHAR(64) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_ivr_settings_organization (organization_id),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organization_ivr_options (
            id INT AUTO_INCREMENT PRIMARY KEY,
            settings_id INT NOT NULL,
            digit CHAR(1) NOT NULL,
            label VARCHAR(80) NOT NULL,
            campaign_id INT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INT NOT NULL DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_ivr_option_digit (settings_id,digit),
            INDEX idx_ivr_option_active (settings_id,is_active,sort_order),
            FOREIGN KEY (settings_id) REFERENCES organization_ivr_settings(id) ON DELETE CASCADE,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE RESTRICT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS call_ivr_selections (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            call_log_id INT NOT NULL,
            menu_option_id INT NOT NULL,
            digit CHAR(1) NOT NULL,
            label VARCHAR(80) NOT NULL,
            campaign_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_call_ivr_selection (call_log_id),
            INDEX idx_call_ivr_org_created (organization_id,created_at),
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
            FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
            FOREIGN KEY (menu_option_id) REFERENCES organization_ivr_options(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    """)

    # An IVR option can route to an AI campaign OR straight to a human
    # destination; exactly one of campaign_id/destination_id is required
    # (enforced in the Pydantic schema, not the database).
    cursor.execute("SHOW COLUMNS FROM organization_ivr_options")
    ivr_option_columns = [col["Field"] for col in cursor.fetchall()]
    if "destination_id" not in ivr_option_columns:
        cursor.execute("ALTER TABLE organization_ivr_options MODIFY COLUMN campaign_id INT NULL")
        cursor.execute("ALTER TABLE organization_ivr_options ADD COLUMN destination_id INT NULL")
        cursor.execute(
            "ALTER TABLE organization_ivr_options ADD CONSTRAINT fk_ivr_option_destination "
            "FOREIGN KEY (destination_id) REFERENCES staff_destinations(id) ON DELETE RESTRICT"
        )
    cursor.execute("SHOW COLUMNS FROM call_ivr_selections")
    ivr_selection_columns = [col["Field"] for col in cursor.fetchall()]
    if "destination_id" not in ivr_selection_columns:
        cursor.execute("ALTER TABLE call_ivr_selections MODIFY COLUMN campaign_id INT NULL")
        cursor.execute("ALTER TABLE call_ivr_selections ADD COLUMN destination_id INT NULL")
        cursor.execute(
            "ALTER TABLE call_ivr_selections ADD CONSTRAINT fk_ivr_selection_destination "
            "FOREIGN KEY (destination_id) REFERENCES staff_destinations(id)"
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runtime_worker_heartbeats (
            worker_name VARCHAR(80) PRIMARY KEY,
            worker_id VARCHAR(191) NOT NULL,
            last_seen_at DATETIME NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_runtime_heartbeat_seen (last_seen_at)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            organization_id INT NOT NULL,
            lang VARCHAR(5) NOT NULL DEFAULT 'en',
            collection VARCHAR(50) NOT NULL,
            doc_id VARCHAR(190) NOT NULL,
            chunk_index INT NOT NULL,
            chunk_text MEDIUMTEXT NOT NULL,
            metadata_json TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_org_doc_chunk (organization_id, doc_id, chunk_index),
            INDEX idx_org_lang (organization_id, lang)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_sites (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, organization_id INT NOT NULL,
            name VARCHAR(180) NOT NULL, code VARCHAR(80) NOT NULL,
            timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_facility_site_code (organization_id,code),
            INDEX idx_facility_site_org (organization_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_assets (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, site_id BIGINT NOT NULL,
            asset_code VARCHAR(100) NOT NULL, name VARCHAR(180) NOT NULL,
            asset_type VARCHAR(80) NOT NULL,
            status ENUM('operational','degraded','offline','maintenance') NOT NULL DEFAULT 'operational',
            location VARCHAR(180) NULL, metadata_json JSON NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_facility_asset_code (site_id,asset_code),
            INDEX idx_facility_asset_site_status (site_id,status),
            FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_sensor_readings (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, site_id BIGINT NOT NULL,
            asset_id BIGINT NULL, sensor_code VARCHAR(100) NOT NULL,
            metric VARCHAR(80) NOT NULL, value DECIMAL(14,4) NOT NULL,
            unit VARCHAR(32) NOT NULL, observed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_facility_sensor_site_observed (site_id,observed_at),
            INDEX idx_facility_sensor_asset_metric (asset_id,metric,observed_at),
            FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_alerts (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, site_id BIGINT NOT NULL,
            asset_id BIGINT NULL, severity ENUM('critical','high','medium','low') NOT NULL,
            title VARCHAR(255) NOT NULL, message TEXT NOT NULL,
            status ENUM('active','acknowledged','resolved') NOT NULL DEFAULT 'active',
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resolved_at TIMESTAMP NULL,
            INDEX idx_facility_alert_site_status (site_id,status,severity),
            FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_service_requests (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, site_id BIGINT NOT NULL,
            asset_id BIGINT NULL, request_number VARCHAR(64) NOT NULL UNIQUE,
            title VARCHAR(255) NOT NULL, description TEXT NOT NULL,
            priority ENUM('critical','high','medium','low') NOT NULL DEFAULT 'medium',
            status ENUM('open','in_progress','resolved','cancelled') NOT NULL DEFAULT 'open',
            requested_by_user_id INT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_facility_request_site_status (site_id,status),
            FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_asset_relationships (
            id BIGINT AUTO_INCREMENT PRIMARY KEY, from_asset_id BIGINT NOT NULL,
            to_asset_id BIGINT NOT NULL, relationship_type VARCHAR(80) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_facility_asset_relationship (from_asset_id,to_asset_id,relationship_type),
            INDEX idx_facility_relationship_to (to_asset_id),
            FOREIGN KEY (from_asset_id) REFERENCES facility_assets(id) ON DELETE CASCADE,
            FOREIGN KEY (to_asset_id) REFERENCES facility_assets(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_action_confirmations (
            id CHAR(36) PRIMARY KEY, organization_id INT NOT NULL,
            requested_by_user_id INT NOT NULL, action_type VARCHAR(80) NOT NULL,
            payload_json JSON NOT NULL,
            status ENUM('pending','approved','consumed','expired','rejected') NOT NULL DEFAULT 'pending',
            expires_at DATETIME NOT NULL, consumed_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_facility_confirmation_lookup (organization_id,requested_by_user_id,status,expires_at)
        )
    """)

    conn.commit()
    conn.close()

def get_db_connection() -> pymysql.Connection:
    """Creates and returns a connection to the MySQL database with dict cursor factory."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def get_db() -> Generator[pymysql.Connection, None, None]:
    """Dependency generator that yields a database connection and ensures it is closed after use."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
