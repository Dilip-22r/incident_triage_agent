"""Tests for app.py REST API — FastAPI TestClient + mocked agent."""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage


@pytest.fixture(autouse=True)
def mock_agent(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr("app._agent", m)
    monkeypatch.setattr("app.get_agent", lambda: m)
    return m


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app import fastapi_app
    return TestClient(fastapi_app)


# /healthz ────────────────────────────────────────────────────────────────────
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# /chat COMPLETED ──────────────────────────────────────────────────────────────
def test_chat_completed(client, mock_agent):
    msg = AIMessage(content="Auth is DEGRADED.", tool_calls=[])
    mock_agent.invoke.return_value = {"messages": [msg]}
    state = MagicMock(); state.next = []
    mock_agent.get_state.return_value = state

    r = client.post("/chat", json={"thread_id": "t1", "message": "auth down"})
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETED"


# /chat AWAITING_APPROVAL ─────────────────────────────────────────────────────
def test_chat_awaiting_approval(client, mock_agent):
    msg = AIMessage(
        content="Escalating.",
        tool_calls=[{"name": "escalate_ticket", "id": "tc1",
                     "args": {"ticket_title": "Auth", "severity": "high"}}],
    )
    mock_agent.invoke.return_value = {"messages": [msg]}
    state = MagicMock(); state.next = ["sensitive_tools"]
    mock_agent.get_state.return_value = state

    r = client.post("/chat", json={"thread_id": "t2", "message": "escalate"})
    assert r.status_code == 200
    assert r.json()["status"] == "AWAITING_APPROVAL"
    assert r.json()["pending_action"] == "escalate_ticket"


# /approve approved ───────────────────────────────────────────────────────────
def test_approve_resolves(client, mock_agent):
    state = MagicMock(); state.next = ["sensitive_tools"]
    mock_agent.get_state.return_value = state
    final = AIMessage(content="Ticket created.", tool_calls=[])
    mock_agent.invoke.return_value = {"messages": [final]}

    r = client.post("/approve", json={"thread_id": "t3", "approved": True})
    assert r.status_code == 200
    assert r.json()["status"] == "RESOLVED"


# /approve rejected ───────────────────────────────────────────────────────────
def test_approve_rejected(client, mock_agent):
    paused = AIMessage(content="Esc.", tool_calls=[
        {"name": "escalate_ticket", "id": "tc5", "args": {}}])
    state = MagicMock()
    state.next = ["sensitive_tools"]
    state.values = {"messages": [paused]}
    mock_agent.get_state.return_value = state
    resume = AIMessage(content="Will monitor.", tool_calls=[])
    mock_agent.invoke.return_value = {"messages": [resume]}

    r = client.post("/approve", json={"thread_id": "t4", "approved": False, "rejection_reason": "Not now"})
    assert r.status_code == 200
    assert r.json()["status"] == "REJECTED_AND_RESUMED"


# /approve 400 when nothing pending ───────────────────────────────────────────
def test_approve_400_when_nothing_pending(client, mock_agent):
    state = MagicMock(); state.next = []
    mock_agent.get_state.return_value = state

    r = client.post("/approve", json={"thread_id": "t5", "approved": True})
    assert r.status_code == 400
