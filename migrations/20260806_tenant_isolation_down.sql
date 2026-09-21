DROP INDEX uq_customer_tenant_email ON customers;
CREATE UNIQUE INDEX email ON customers (email);
