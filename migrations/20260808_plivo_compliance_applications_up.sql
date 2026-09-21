-- Adds automated Plivo India number provisioning: per-organization compliance
-- (KYC) application tracking, leading to an auto-created Plivo subaccount and
-- a purchased number once Plivo approves the application.
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
);
