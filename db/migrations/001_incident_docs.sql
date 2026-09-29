-- db/migrations/001_incident_docs.sql
-- Run this in Supabase SQL Editor

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create incident_docs table
CREATE TABLE IF NOT EXISTS incident_docs (
    id          BIGSERIAL PRIMARY KEY,
    content     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    embedding   vector(768),
    content_hash TEXT GENERATED ALWAYS AS (md5(content)) STORED,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint on content_hash → idempotent seeding
CREATE UNIQUE INDEX IF NOT EXISTS incident_docs_content_hash_idx
    ON incident_docs(content_hash);

-- Cosine-similarity search function
CREATE OR REPLACE FUNCTION match_incident_docs(
    query_embedding vector(768),
    match_count     INT  DEFAULT 5,
    filter          JSONB DEFAULT '{}'
)
RETURNS TABLE (
    id          BIGINT,
    content     TEXT,
    metadata    JSONB,
    similarity  FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        incident_docs.id,
        incident_docs.content,
        incident_docs.metadata,
        1 - (incident_docs.embedding <=> query_embedding) AS similarity
    FROM incident_docs
    WHERE incident_docs.metadata @> filter
    ORDER BY incident_docs.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
