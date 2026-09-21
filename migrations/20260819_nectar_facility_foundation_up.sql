-- Nectar Facility Operations foundation. All operational records are scoped
-- through facility_sites.organization_id; no facility fact is globally shared.
CREATE TABLE IF NOT EXISTS facility_sites (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    name VARCHAR(180) NOT NULL,
    code VARCHAR(80) NOT NULL,
    timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_facility_site_code (organization_id, code),
    INDEX idx_facility_site_org (organization_id)
);

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
    CONSTRAINT fk_facility_asset_site FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE
);

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
    CONSTRAINT fk_facility_sensor_site FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
    CONSTRAINT fk_facility_sensor_asset FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
);

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
    CONSTRAINT fk_facility_alert_site FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
    CONSTRAINT fk_facility_alert_asset FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
);

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
    CONSTRAINT fk_facility_request_site FOREIGN KEY (site_id) REFERENCES facility_sites(id) ON DELETE CASCADE,
    CONSTRAINT fk_facility_request_asset FOREIGN KEY (asset_id) REFERENCES facility_assets(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS facility_asset_relationships (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    from_asset_id BIGINT NOT NULL,
    to_asset_id BIGINT NOT NULL,
    relationship_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_facility_asset_relationship (from_asset_id, to_asset_id, relationship_type),
    INDEX idx_facility_relationship_to (to_asset_id),
    CONSTRAINT fk_facility_relationship_from FOREIGN KEY (from_asset_id) REFERENCES facility_assets(id) ON DELETE CASCADE,
    CONSTRAINT fk_facility_relationship_to FOREIGN KEY (to_asset_id) REFERENCES facility_assets(id) ON DELETE CASCADE
);
