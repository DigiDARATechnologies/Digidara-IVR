CREATE TABLE IF NOT EXISTS runtime_worker_heartbeats (
    worker_name VARCHAR(80) PRIMARY KEY,
    worker_id VARCHAR(191) NOT NULL,
    last_seen_at DATETIME NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_runtime_heartbeat_seen (last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
