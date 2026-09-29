"""Tests for agent.py — mocks LLM + DB; covers routing, HITL, persistence."""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END

from agent import route_tools, extract_text, AgentState, SENSITIVE_NAMES


# ── extract_text ──────────────────────────────────────────────────────────────
def test_extract_text_string():
    assert extract_text("hello") == "hello"

def test_extract_text_list():
    assert extract_text([{"text": "foo"}, "bar"]) == "foo bar"

def test_extract_text_fallback():
    assert extract_text(99) == "99"


# ── route_tools ───────────────────────────────────────────────────────────────
def _ai(tool_calls):
    m = MagicMock(spec=AIMessage)
    m.tool_calls = tool_calls
    return m

def test_route_safe():
    state: AgentState = {"messages": [_ai([{"name": "query_service_health", "id": "1", "args": {}}])]}
    assert route_tools(state) == "safe_tools"

def test_route_sensitive():
    state: AgentState = {"messages": [_ai([{"name": "escalate_ticket", "id": "2", "args": {}}])]}
    assert route_tools(state) == "sensitive_tools"

def test_route_mixed_goes_sensitive():
    """Change 6: ANY sensitive call → sensitive_tools."""
    state: AgentState = {"messages": [_ai([
        {"name": "query_service_health", "id": "1", "args": {}},
        {"name": "escalate_ticket",      "id": "2", "args": {}},
    ])]}
    assert route_tools(state) == "sensitive_tools"

def test_route_no_calls_ends():
    state: AgentState = {"messages": [_ai([])]}
    assert route_tools(state) == END


# ── Full-graph tests (MemorySaver, no real DB) ────────────────────────────────
@patch("agent.get_pool")
@patch("agent.get_llm")
def test_safe_path_completes(mock_llm, mock_pool):
    health_call = AIMessage(
        content="Checking…",
        tool_calls=[{"name": "query_service_health", "id": "tc1", "args": {"service_name": "auth"}}],
    )
    final = AIMessage(content="Auth is DEGRADED. Restart Redis.", tool_calls=[])
    mock_llm.return_value.invoke.side_effect = [health_call, final]

    from agent import get_agent_app
    app    = get_agent_app(checkpointer=MemorySaver())
    result = app.invoke(
        {"messages": [HumanMessage(content="auth down")]},
        {"configurable": {"thread_id": "safe-1"}},
    )
    assert "DEGRADED" in result["messages"][-1].content


@patch("agent.get_pool")
@patch("agent.get_llm")
def test_hitl_pauses(mock_llm, mock_pool):
    esc = AIMessage(
        content="Escalating.",
        tool_calls=[{"name": "escalate_ticket", "id": "tc2",
                     "args": {"ticket_title": "Auth 504", "severity": "high"}}],
    )
    mock_llm.return_value.invoke.return_value = esc

    from agent import get_agent_app
    app    = get_agent_app(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "hitl-pause"}}
    app.invoke({"messages": [HumanMessage(content="escalate")]}, config)
    state = app.get_state(config)
    assert "sensitive_tools" in state.next


@patch("agent.get_pool")
@patch("agent.get_llm")
def test_hitl_approve(mock_llm, mock_pool):
    esc   = AIMessage(content="Escalating.", tool_calls=[
        {"name": "escalate_ticket", "id": "tc3",
         "args": {"ticket_title": "Auth 504", "severity": "high"}}])
    final = AIMessage(content="Ticket created.", tool_calls=[])
    mock_llm.return_value.invoke.side_effect = [esc, final]

    from agent import get_agent_app
    app    = get_agent_app(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "hitl-approve"}}
    app.invoke({"messages": [HumanMessage(content="escalate")]}, config)
    result = app.invoke(None, config)
    assert "Ticket" in result["messages"][-1].content


@patch("agent.get_pool")
@patch("agent.get_llm")
def test_hitl_reject(mock_llm, mock_pool):
    esc    = AIMessage(content="Escalating.", tool_calls=[
        {"name": "escalate_ticket", "id": "tc4",
         "args": {"ticket_title": "Auth 504", "severity": "high"}}])
    resume = AIMessage(content="Will monitor.", tool_calls=[])
    mock_llm.return_value.invoke.side_effect = [esc, resume]

    from agent import get_agent_app
    app    = get_agent_app(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "hitl-reject"}}
    app.invoke({"messages": [HumanMessage(content="escalate")]}, config)

    reject_msg = ToolMessage(content="Rejected by engineer: not critical", tool_call_id="tc4")
    app.update_state(config, {"messages": [reject_msg]}, as_node="sensitive_tools")
    result = app.invoke(None, config)
    assert "monitor" in result["messages"][-1].content.lower()


@patch("agent.get_pool")
@patch("agent.get_llm")
def test_thread_isolation(mock_llm, mock_pool):
    a = AIMessage(content="Auth DEGRADED.",  tool_calls=[])
    b = AIMessage(content="Payments fine.", tool_calls=[])
    mock_llm.return_value.invoke.side_effect = [a, b]

    from agent import get_agent_app
    app = get_agent_app(checkpointer=MemorySaver())
    r1  = app.invoke({"messages": [HumanMessage(content="auth")]},     {"configurable": {"thread_id": "A"}})
    r2  = app.invoke({"messages": [HumanMessage(content="payments")]}, {"configurable": {"thread_id": "B"}})
    assert r1["messages"][-1].content != r2["messages"][-1].content
