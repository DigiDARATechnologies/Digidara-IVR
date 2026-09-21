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
