-- Replaces the single global PLIVO_INBOUND_CAMPAIGN_ID env var with a real
-- DID -> tenant mapping, so multiple businesses can each own their own Plivo
-- number and have inbound calls route to their own organization/campaign.
--
-- campaign_id stays a required FK (matching call_logs.campaign_id NOT NULL)
-- so the existing call-logging and stream-token plumbing is untouched; a
-- number cannot be activated for inbound routing until an inbound campaign
-- has been assigned to it.
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
);
