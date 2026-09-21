CREATE TABLE IF NOT EXISTS organization_ivr_settings (
    id INT AUTO_INCREMENT PRIMARY KEY, organization_id INT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE, timeout_seconds TINYINT NOT NULL DEFAULT 7,
    prompt_english VARCHAR(500) NOT NULL DEFAULT '', prompt_tamil VARCHAR(500) NOT NULL DEFAULT '',
    audio_token VARCHAR(64) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ivr_settings_organization (organization_id),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS organization_ivr_options (
    id INT AUTO_INCREMENT PRIMARY KEY, settings_id INT NOT NULL, digit CHAR(1) NOT NULL,
    label VARCHAR(80) NOT NULL, campaign_id INT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 100, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ivr_option_digit (settings_id,digit), INDEX idx_ivr_option_active (settings_id,is_active,sort_order),
    FOREIGN KEY (settings_id) REFERENCES organization_ivr_settings(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS call_ivr_selections (
    id BIGINT AUTO_INCREMENT PRIMARY KEY, organization_id INT NOT NULL, call_log_id INT NOT NULL,
    menu_option_id INT NOT NULL, digit CHAR(1) NOT NULL, label VARCHAR(80) NOT NULL, campaign_id INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE KEY uq_call_ivr_selection (call_log_id),
    INDEX idx_call_ivr_org_created (organization_id,created_at),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (call_log_id) REFERENCES call_logs(id) ON DELETE CASCADE,
    FOREIGN KEY (menu_option_id) REFERENCES organization_ivr_options(id), FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
