-- Production callback workflow. Apply after a database backup.
-- Compatible with the earlier minimal followup_reminders table.

CREATE TABLE IF NOT EXISTS followup_reminders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NULL,
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
    idempotency_key VARCHAR(191) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
    FOREIGN KEY (source_call_log_id) REFERENCES call_logs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE followup_reminders
    ADD COLUMN IF NOT EXISTS organization_id INT NULL AFTER id,
    ADD COLUMN IF NOT EXISTS source VARCHAR(40) NOT NULL DEFAULT 'post_call_analysis' AFTER reminder_type,
    ADD COLUMN IF NOT EXISTS requested_date DATE NULL AFTER source,
    ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata' AFTER scheduled_at,
    ADD COLUMN IF NOT EXISTS assigned_user_id INT NULL AFTER status,
    ADD COLUMN IF NOT EXISTS completed_by_user_id INT NULL AFTER completed_at,
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(191) NULL AFTER completed_by_user_id,
    MODIFY COLUMN scheduled_at DATETIME NULL;

UPDATE followup_reminders fr
JOIN customers c ON c.id=fr.customer_id
SET fr.organization_id=c.organization_id
WHERE fr.organization_id IS NULL;

UPDATE followup_reminders
SET idempotency_key=CONCAT('legacy:callback:',id)
WHERE idempotency_key IS NULL OR idempotency_key='';

ALTER TABLE followup_reminders
    MODIFY COLUMN organization_id INT NOT NULL,
    MODIFY COLUMN idempotency_key VARCHAR(191) NOT NULL;

SET @db_name = DATABASE();
SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='followup_reminders' AND INDEX_NAME='uq_followup_idempotency')=0,
  'CREATE UNIQUE INDEX uq_followup_idempotency ON followup_reminders(idempotency_key)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='followup_reminders' AND INDEX_NAME='idx_reminder_tenant_status_due')=0,
  'CREATE INDEX idx_reminder_tenant_status_due ON followup_reminders(organization_id,status,scheduled_at)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='followup_reminders' AND INDEX_NAME='idx_reminder_assignee_status')=0,
  'CREATE INDEX idx_reminder_assignee_status ON followup_reminders(organization_id,assigned_user_id,status)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

