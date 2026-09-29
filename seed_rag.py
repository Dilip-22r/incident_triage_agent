"""
seed_rag.py
Embeds 3 sample runbooks (auth, database, payments) and inserts them into
Supabase pgvector. Re-running is safe — ON CONFLICT DO NOTHING (idempotent).
"""
import os
import psycopg
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DATABASE_URL   = os.environ["DATABASE_URL"]

RUNBOOKS = [
    {
        "content": (
            "# Auth Service 504 Timeout Runbook\n"
            "## Symptoms\n"
            "- Auth service returning 504 Gateway Timeout errors\n"
            "- Login requests failing after 30 seconds\n"
            "- Increased latency on /api/auth/token endpoint\n\n"
            "## Diagnosis\n"
            "1. Check Redis cache: `redis-cli ping`\n"
            "2. Verify JWT signing service health\n"
            "3. Check DB connection pool saturation\n\n"
            "## Remediation\n"
            "1. Restart Redis: `systemctl restart redis`\n"
            "2. Clear token cache: `redis-cli FLUSHDB`\n"
            "3. Scale auth pods if CPU > 80 %\n\n"
            "## Escalation Criteria\n"
            "Escalate if service stays degraded > 10 min or cache clear fails."
        ),
        "metadata": {"service": "auth", "type": "runbook", "severity": "high"},
    },
    {
        "content": (
            "# Database High Latency Runbook\n"
            "## Symptoms\n"
            "- Query response times > 500 ms (normal < 50 ms)\n"
            "- Connection pool exhaustion alerts\n"
            "- Slow-query log shows full table scans\n\n"
            "## Diagnosis\n"
            "1. Check pg_stat_activity for blocking queries\n"
            "2. Review slow queries via pg_stat_statements\n"
            "3. Monitor disk I/O with iostat\n\n"
            "## Remediation\n"
            "1. Kill long-running blocking queries\n"
            "2. VACUUM ANALYZE affected tables\n"
            "3. Add missing indexes\n\n"
            "## Escalation Criteria\n"
            "Escalate if replication lag > 1 min or disk < 10 %."
        ),
        "metadata": {"service": "database", "type": "runbook", "severity": "high"},
    },
    {
        "content": (
            "# Payment Gateway Failure Runbook\n"
            "## Symptoms\n"
            "- Payment transactions failing with 502/503\n"
            "- Stripe/PayPal webhook timeouts\n"
            "- Order completion rate < 95 %\n\n"
            "## Diagnosis\n"
            "1. Check gateway status page\n"
            "2. Verify API key validity and rate limits\n"
            "3. Test outbound connectivity: `curl -I https://api.stripe.com`\n\n"
            "## Remediation\n"
            "1. Switch to backup payment provider if configured\n"
            "2. Queue failed transactions for retry with backoff\n"
            "3. Enable maintenance mode\n\n"
            "## Escalation Criteria\n"
            "Escalate if > 50 failed transactions in 5 min or revenue impact > $1 000."
        ),
        "metadata": {"service": "payments", "type": "runbook", "severity": "critical"},
    },
]


def get_embeddings_client():
    return GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=GEMINI_API_KEY,
        task_type="RETRIEVAL_DOCUMENT",
    )


def seed_runbooks(db_url: str = None, embeddings_client=None) -> int:
    """Seed runbooks. Returns number of newly inserted rows (0 = already seeded)."""
    url    = db_url or DATABASE_URL
    client = embeddings_client or get_embeddings_client()

    contents   = [r["content"] for r in RUNBOOKS]
    print("Generating embeddings …")
    embeddings = client.embed_documents(contents)

    inserted = 0
    with psycopg.connect(url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            for runbook, emb in zip(RUNBOOKS, embeddings):
                cur.execute(
                    """
                    INSERT INTO incident_docs (content, metadata, embedding)
                    VALUES (%s, %s, %s::vector)
                    ON CONFLICT (content_hash) DO NOTHING
                    """,
                    (runbook["content"], Jsonb(runbook["metadata"]), str(emb)),
                )
                inserted += cur.rowcount
        conn.commit()

    print(f"Inserted {inserted} new runbook(s). (0 means already present — idempotent ✓)")
    return inserted


if __name__ == "__main__":
    seed_runbooks()
