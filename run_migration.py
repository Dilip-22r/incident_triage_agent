"""update_schema.py — recreates incident_docs table with correct vector dimension for gemini-embedding-001 (3072 dims)."""
import psycopg, os
from dotenv import load_dotenv

load_dotenv()
url = os.environ["DATABASE_URL"]

FUNC_SQL = """
    CREATE OR REPLACE FUNCTION match_incident_docs(
        query_embedding vector(3072),
        match_count     INT  DEFAULT 5,
        filter          JSONB DEFAULT '{}'
    )
    RETURNS TABLE (
        id          BIGINT,
        content     TEXT,
        metadata    JSONB,
        similarity  FLOAT
    )
    LANGUAGE plpgsql AS
    $$
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
    $$
"""

print("Updating schema to vector(3072) for gemini-embedding-001...")
with psycopg.connect(url, prepare_threshold=None, autocommit=True) as conn:
    conn.execute("DROP TABLE IF EXISTS incident_docs CASCADE")
    print("  [1] Dropped old table")

    conn.execute("""
        CREATE TABLE incident_docs (
            id           BIGSERIAL PRIMARY KEY,
            content      TEXT NOT NULL,
            metadata     JSONB DEFAULT '{}',
            embedding    vector(3072),
            content_hash TEXT GENERATED ALWAYS AS (md5(content)) STORED,
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    print("  [2] Created incident_docs with vector(3072)")

    conn.execute("""
        CREATE UNIQUE INDEX incident_docs_content_hash_idx
        ON incident_docs(content_hash)
    """)
    print("  [3] Unique index: OK")

    conn.execute(FUNC_SQL)
    print("  [4] match_incident_docs(vector(3072)): OK")

print("\nSchema updated! Now ready to seed.")
