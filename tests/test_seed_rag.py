"""Tests for seed_rag.py — mocks Gemini embeddings + psycopg DB."""
import pytest
from unittest.mock import MagicMock, patch
from seed_rag import seed_runbooks, RUNBOOKS

FAKE_EMB = [0.1] * 768


@pytest.fixture
def mock_emb():
    c = MagicMock()
    c.embed_documents.return_value = [FAKE_EMB] * len(RUNBOOKS)
    return c


def _conn_ctx(rowcount=1):
    cur = MagicMock()
    cur.rowcount = rowcount
    ctx_cur = MagicMock()
    ctx_cur.__enter__ = MagicMock(return_value=cur)
    ctx_cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = ctx_cur
    conn.commit = MagicMock()
    ctx_conn = MagicMock()
    ctx_conn.__enter__ = MagicMock(return_value=conn)
    ctx_conn.__exit__ = MagicMock(return_value=False)
    return ctx_conn, cur


def test_seed_inserts_all_runbooks(mock_emb):
    ctx_conn, cur = _conn_ctx(rowcount=1)
    with patch("seed_rag.psycopg.connect", return_value=ctx_conn):
        n = seed_runbooks(db_url="postgresql://fake", embeddings_client=mock_emb)
    assert n == len(RUNBOOKS)
    mock_emb.embed_documents.assert_called_once()


def test_seed_idempotent(mock_emb):
    """Re-running returns 0 (ON CONFLICT DO NOTHING)."""
    ctx_conn, cur = _conn_ctx(rowcount=0)
    with patch("seed_rag.psycopg.connect", return_value=ctx_conn):
        n = seed_runbooks(db_url="postgresql://fake", embeddings_client=mock_emb)
    assert n == 0


def test_seed_uses_retrieval_document_task_type():
    with patch("seed_rag.GoogleGenerativeAIEmbeddings") as MockEmb:
        inst = MagicMock()
        inst.embed_documents.return_value = [FAKE_EMB] * len(RUNBOOKS)
        MockEmb.return_value = inst
        with patch("seed_rag.psycopg.connect"):
            try:
                seed_runbooks(db_url="postgresql://fake")
            except Exception:
                pass
        kw = MockEmb.call_args[1]
        assert kw.get("task_type") == "RETRIEVAL_DOCUMENT"
