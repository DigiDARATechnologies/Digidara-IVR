-- Preserves callback rows while removing workflow-only indexes and fields.
DROP INDEX idx_reminder_assignee_status ON followup_reminders;
DROP INDEX idx_reminder_tenant_status_due ON followup_reminders;
DROP INDEX uq_followup_idempotency ON followup_reminders;
ALTER TABLE followup_reminders
    DROP COLUMN idempotency_key,
    DROP COLUMN completed_by_user_id,
    DROP COLUMN assigned_user_id,
    DROP COLUMN timezone,
    DROP COLUMN requested_date,
    DROP COLUMN source,
    DROP COLUMN organization_id;

