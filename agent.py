"""
agent.py
LangGraph Autonomous Incident Triage Agent.

Graph:  agent ──► route_tools ──► safe_tools   ──► agent
                              └──► sensitive_tools (interrupt_before, HITL)

Change 6 (harden-hitl-routing): route_tools checks ALL tool calls, not just [0].
"""
import os
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from psycopg_pool import ConnectionPool
from typing_extensions import TypedDict

load_dotenv()

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DATABASE_URL   = os.environ["DATABASE_URL"]

# ── Connection pool (transaction pooler needs prepare_threshold=None) ───────
_pool: ConnectionPool | None = None

def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": None,
                "connect_timeout": 15,
            },
        )
    return _pool


# ── Helpers ─────────────────────────────────────────────────────────────────
def extract_text(content: Any) -> str:
    """Flatten list-structured model content to plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(content)


# ── Mocked service health table ──────────────────────────────────────────────
SERVICE_HEALTH = {
    "auth":        "DEGRADED — 504 timeouts; Redis cache latency elevated.",
    "database":    "HEALTHY — all replicas in sync, latency < 10 ms.",
    "payments":    "DEGRADED — 502 errors; upstream provider issue suspected.",
    "api-gateway": "HEALTHY — all routes responding normally.",
}


# ── Tools ────────────────────────────────────────────────────────────────────
@tool
def query_service_health(service_name: str) -> str:
    """Return current health status of a named backend service.

    Args:
        service_name: e.g. 'auth', 'database', 'payments'.
    """
    status = SERVICE_HEALTH.get(service_name.lower())
    if status is None:
        known = ", ".join(SERVICE_HEALTH.keys())
        return f"Service '{service_name}' not found. Known: {known}."
    return f"[{service_name.upper()}] {status}"


@tool
def search_remediation_runbooks(query: str) -> str:
    """Search the runbook knowledge base for remediation steps.

    Args:
        query: Plain-English incident description.
    """
    try:
        emb_client = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-2",
            google_api_key=GEMINI_API_KEY,
            task_type="RETRIEVAL_QUERY",
        )
        vec = emb_client.embed_query(query)
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content, metadata, 1-(embedding <=> %s::vector) AS sim "
                    "FROM incident_docs ORDER BY embedding <=> %s::vector LIMIT 2",
                    (str(vec), str(vec)),
                )
                rows = cur.fetchall()
        if not rows:
            return "No relevant runbooks found."
        return "\n\n---\n\n".join(
            f"[{(r[1] or {}).get('service','?').upper()} | sim={r[2]:.2f}]\n{r[0][:600]}"
            for r in rows
        )
    except Exception as exc:
        return f"Runbook search failed: {exc}"


@tool
def escalate_ticket(ticket_title: str, severity: str) -> str:
    """CRITICAL — open an escalation ticket and page on-call. Requires HITL approval.

    Args:
        ticket_title: Short incident description.
        severity: 'low' | 'medium' | 'high' | 'critical'.
    """
    return f"TICKET CREATED: [{severity.upper()}] {ticket_title} — on-call paged."


# ── Tool groups ───────────────────────────────────────────────────────────────
SAFE_TOOLS      = [query_service_health, search_remediation_runbooks]
SENSITIVE_TOOLS = [escalate_ticket]
SENSITIVE_NAMES = {t.name for t in SENSITIVE_TOOLS}
ALL_TOOLS       = SAFE_TOOLS + SENSITIVE_TOOLS


# ── State ────────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# ── LLM ──────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are an autonomous incident triage AI agent.\n"
    "1. ALWAYS call query_service_health first.\n"
    "2. Then search_remediation_runbooks.\n"
    "3. Summarise health + runbook findings.\n"
    "4. If manual intervention is needed OR the service stays degraded, "
    "use escalate_ticket — this REQUIRES engineer approval.\n"
    "Never escalate without the approval process."
)


def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=GEMINI_API_KEY,
        temperature=0,
    ).bind_tools(ALL_TOOLS)


# ── Nodes ────────────────────────────────────────────────────────────────────
def agent_node(state: AgentState):
    llm = get_llm()
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])
    return {"messages": [response]}


def safe_tools_node(state: AgentState):
    tool_map = {t.name: t for t in SAFE_TOOLS}
    last = state["messages"][-1]
    results = []
    for tc in last.tool_calls:
        if tc["name"] in tool_map:
            out = tool_map[tc["name"]].invoke(tc["args"])
            results.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
    return {"messages": results}


def sensitive_tools_node(state: AgentState):
    tool_map = {t.name: t for t in SENSITIVE_TOOLS}
    last = state["messages"][-1]
    results = []
    for tc in last.tool_calls:
        if tc["name"] in tool_map:
            out = tool_map[tc["name"]].invoke(tc["args"])
            results.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
    return {"messages": results}


# ── Routing (Change 6: checks ALL tool calls) ─────────────────────────────
def route_tools(state: AgentState) -> str:
    last = state["messages"][-1]
    if not getattr(last, "tool_calls", None):
        return END
    if any(tc["name"] in SENSITIVE_NAMES for tc in last.tool_calls):
        return "sensitive_tools"
    return "safe_tools"


# ── Graph factory ─────────────────────────────────────────────────────────────
def get_agent_app(checkpointer=None):
    """Compile and return the LangGraph agent. Inject checkpointer for testing."""
    builder = StateGraph(AgentState)
    builder.add_node("agent",           agent_node)
    builder.add_node("safe_tools",      safe_tools_node)
    builder.add_node("sensitive_tools", sensitive_tools_node)
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", route_tools)
    builder.add_edge("safe_tools",      "agent")
    builder.add_edge("sensitive_tools", "agent")

    if checkpointer is None:
        pool = get_pool()
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["sensitive_tools"],
    )


if __name__ == "__main__":
    app    = get_agent_app()
    config = {"configurable": {"thread_id": "smoke-1"}}
    result = app.invoke(
        {"messages": [HumanMessage(content="Auth service is timing out")]},
        config,
    )
    print(extract_text(result["messages"][-1].content))
