-- Adds file-upload-based bulk calling (Excel/CSV) as an alternative to
-- Google Sheets. Row identity uses row_index, not row_number, because
-- ROW_NUMBER is a reserved word in MySQL 8 (window functions).
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
);
