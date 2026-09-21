-- Apply after taking a database backup. Mirrors schema.sql and init_db().
--
-- Adds the business-hours gate for inbound calls. An organization with no
-- rows in business_hours is treated as always open (fail-open), so this
-- ships without changing behavior for any tenant until they configure a
-- schedule via PUT /business-hours.
ALTER TABLE organizations
  ADD COLUMN timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata';

CREATE TABLE IF NOT EXISTS business_hours (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    day_of_week TINYINT NOT NULL COMMENT '0=Monday .. 6=Sunday',
    is_closed BOOLEAN NOT NULL DEFAULT FALSE,
    open_time VARCHAR(5) NULL COMMENT '24-hour HH:MM, organization-local time',
    close_time VARCHAR(5) NULL COMMENT '24-hour HH:MM, organization-local time',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_business_hours_org_day (organization_id, day_of_week),
    FOREIGN KEY (organization_id) REFERENCES organizations (id)
);
