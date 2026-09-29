"""
app.py
FastAPI + Gradio UI for the Incident Triage Agent.

Endpoints:
  GET  /healthz   — lightweight health check (no Gemini / DB calls)
  POST /chat      — start triage; returns COMPLETED | AWAITING_APPROVAL
  POST /approve   — resume thread; returns RESOLVED | REJECTED_AND_RESUMED | 400

Gradio Blocks UI is mounted at "/" and shares the same service layer.
Single ASGI object exposed as `app`.
"""
import os
from typing import Optional

import gradio as gr
from fastapi import FastAPI, HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel
from dotenv import load_dotenv

from agent import extract_text, get_agent_app, SENSITIVE_NAMES

load_dotenv()

# ── Singleton agent ───────────────────────────────────────────────────────────
_agent = None

def get_agent():
    global _agent
    if _agent is None:
        _agent = get_agent_app()
    return _agent


# ── FastAPI ───────────────────────────────────────────────────────────────────
fastapi_app = FastAPI(title="Incident Triage Agent", version="1.0.0")


class ChatRequest(BaseModel):
    thread_id: str
    message: str


class ApproveRequest(BaseModel):
    thread_id: str
    approved: bool
    rejection_reason: Optional[str] = None


# ── Shared service layer ──────────────────────────────────────────────────────
def _triage(thread_id: str, message: str) -> dict:
    app    = get_agent()
    config = {"configurable": {"thread_id": thread_id}}
    result = app.invoke({"messages": [HumanMessage(content=message)]}, config)
    state  = app.get_state(config)
    last   = result["messages"][-1]

    if state.next and "sensitive_tools" in state.next:
        pending = [
            {"name": tc["name"], "args": tc["args"]}
            for tc in (getattr(last, "tool_calls", None) or [])
            if tc["name"] in SENSITIVE_NAMES
        ]
        return {
            "status":         "AWAITING_APPROVAL",
            "thread_id":      thread_id,
            "pending_action": pending[0]["name"] if pending else "escalate_ticket",
            "parameters":     pending[0]["args"]  if pending else {},
            "message":        extract_text(last.content),
        }
    return {
        "status":    "COMPLETED",
        "thread_id": thread_id,
        "message":   extract_text(last.content),
    }


def _approve(thread_id: str, approved: bool, reason: str = None) -> dict:
    app    = get_agent()
    config = {"configurable": {"thread_id": thread_id}}
    state  = app.get_state(config)

    if not (state.next and "sensitive_tools" in state.next):
        raise HTTPException(400, f"No pending approval for thread '{thread_id}'.")

    if approved:
        result = app.invoke(None, config)
        return {
            "status":    "RESOLVED",
            "thread_id": thread_id,
            "message":   extract_text(result["messages"][-1].content),
        }

    # Rejection: answer every pending sensitive tool call
    last_ai = state.values["messages"][-1]
    rejects = [
        ToolMessage(
            content=f"Rejected by engineer: {reason or 'No reason given.'}",
            tool_call_id=tc["id"],
        )
        for tc in (getattr(last_ai, "tool_calls", None) or [])
        if tc["name"] in SENSITIVE_NAMES
    ]
    app.update_state(config, {"messages": rejects}, as_node="sensitive_tools")
    result = app.invoke(None, config)
    return {
        "status":    "REJECTED_AND_RESUMED",
        "thread_id": thread_id,
        "message":   extract_text(result["messages"][-1].content),
    }


# ── REST endpoints ────────────────────────────────────────────────────────────
@fastapi_app.get("/healthz")
def healthz():
    return {"status": "ok"}


@fastapi_app.post("/chat")
def chat(req: ChatRequest):
    try:
        return _triage(req.thread_id, req.message)
    except Exception as exc:
        raise HTTPException(500, str(exc))


@fastapi_app.post("/approve")
def approve(req: ApproveRequest):
    return _approve(req.thread_id, req.approved, req.rejection_reason)


# ── Gradio UI ─────────────────────────────────────────────────────────────────
def ui_triage(tid: str, msg: str):
    if not tid.strip():
        return "❌ Thread ID is required.", "ERROR"
    try:
        r = _triage(tid.strip(), msg.strip())
        log = f"**Status:** {r['status']}\n\n{r.get('message','')}"
        if r["status"] == "AWAITING_APPROVAL":
            log += f"\n\n**Pending:** `{r['pending_action']}` — params: `{r['parameters']}`"
        return log, r["status"]
    except Exception as exc:
        return f"❌ {exc}", "ERROR"


def ui_approve(tid: str, reason: str):
    if not tid.strip():
        return "❌ Thread ID is required.", "ERROR"
    try:
        r = _approve(tid.strip(), approved=True)
        return f"**Status:** {r['status']}\n\n{r.get('message','')}", r["status"]
    except HTTPException as exc:
        return f"❌ {exc.detail}", "ERROR"
    except Exception as exc:
        return f"❌ {exc}", "ERROR"


def ui_reject(tid: str, reason: str):
    if not tid.strip():
        return "❌ Thread ID is required.", "ERROR"
    try:
        r = _approve(tid.strip(), approved=False, reason=reason)
        return f"**Status:** {r['status']}\n\n{r.get('message','')}", r["status"]
    except HTTPException as exc:
        return f"❌ {exc.detail}", "ERROR"
    except Exception as exc:
        return f"❌ {exc}", "ERROR"


with gr.Blocks(title="Incident Triage Agent", theme=gr.themes.Soft()) as ui:
    gr.Markdown("# 🚨 Autonomous Incident Triage Agent\n> Describe an incident and let the AI investigate.")
    with gr.Row():
        with gr.Column():
            tid_box = gr.Textbox(label="Thread ID", value="incident-001")
            msg_box = gr.Textbox(
                label="Incident Description",
                value="Auth service is timing out. Escalate immediately.",
                lines=3,
            )
            triage_btn = gr.Button("🔍 Trigger Triage", variant="primary")
        with gr.Column():
            reason_box = gr.Textbox(label="Rejection Reason (optional)")
            approve_btn = gr.Button("✅ Approve Escalation", variant="secondary")
            reject_btn  = gr.Button("❌ Reject Action",      variant="stop")

    log_md = gr.Markdown()
    status_lbl = gr.Label(label="Workflow State", value="IDLE")

    triage_btn.click(ui_triage,  [tid_box, msg_box],          [log_md, status_lbl])
    approve_btn.click(ui_approve, [tid_box, reason_box],       [log_md, status_lbl])
    reject_btn.click(ui_reject,  [tid_box, reason_box],        [log_md, status_lbl])


# ── Mount Gradio → single ASGI object ─────────────────────────────────────────
app = gr.mount_gradio_app(fastapi_app, ui, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
