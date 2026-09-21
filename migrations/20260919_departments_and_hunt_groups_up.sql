-- Dynamic departments and team-based simultaneous ringing (hunt groups)
CREATE TABLE IF NOT EXISTS departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    name VARCHAR(80) NOT NULL,
    description VARCHAR(255) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_department_name (organization_id, name),
    INDEX idx_department_active (organization_id, is_active),
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
);

-- Seed default departments for existing organizations if not already present
INSERT IGNORE INTO departments (organization_id, name, description)
SELECT o.id, d.name, d.description
FROM organizations o
CROSS JOIN (
    SELECT 'Business' AS name, 'Business operations and partnerships' AS description
    UNION ALL SELECT 'Sales', 'Direct sales and inbound inquiries'
    UNION ALL SELECT 'Education', 'Customer education and product advisory'
) d;

-- Also register any custom departments currently present in staff_destinations
INSERT IGNORE INTO departments (organization_id, name)
SELECT DISTINCT organization_id, department
FROM staff_destinations
WHERE department IS NOT NULL AND TRIM(department) != '';
