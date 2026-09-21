ALTER TABLE customers DROP INDEX email;
CREATE UNIQUE INDEX uq_customer_tenant_email
    ON customers (organization_id, email);
