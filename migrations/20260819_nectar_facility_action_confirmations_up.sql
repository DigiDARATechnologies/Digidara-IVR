-- Durable, tenant-scoped confirmation state for operational write actions.
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
    INDEX idx_facility_confirmation_lookup (organization_id, requested_by_user_id, status, expires_at)
);
