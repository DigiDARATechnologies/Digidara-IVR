-- Adds organization-scoped knowledge base chunks that back the in-memory
-- BM25 index used on the live call path (app/livekit_agent/memory_kb.py).
-- Each organization's own uploaded content is merged with the shared
-- DigiDARA baseline (hardcoded seed docs) at index-build time.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    lang VARCHAR(5) NOT NULL DEFAULT 'en',
    collection VARCHAR(50) NOT NULL,
    doc_id VARCHAR(190) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text MEDIUMTEXT NOT NULL,
    metadata_json TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_org_doc_chunk (organization_id, doc_id, chunk_index),
    INDEX idx_org_lang (organization_id, lang)
);
