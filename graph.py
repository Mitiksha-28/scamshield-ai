import os

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from agents.orchestrator import orchestrator_node
from agents.risk_judge import risk_judge_node
from state import AGENTS, ScamState
from tracelog import emit, new_run_id, read_run

load_dotenv()


def _investigators():
    if os.getenv("USE_STUBS") == "1":
        from agents.stubs import price_market_node, reputation_node, web_detective_node
    else:
        from agents.price_market import price_market_node
        from agents.reputation import reputation_node
        from agents.web_detective import web_detective_node
    return {"web_detective": web_detective_node, "reputation": reputation_node,
            "price_market": price_market_node}


def route_after_orchestrator(state):
    """Adaptive routing: back to the agents named in re-verification requests, else on to the judge."""
    reqs = state.get("requests") or {}
    return list(reqs) if reqs else "risk_judge"


def build_graph():
    g = StateGraph(ScamState)
    for name, fn in _investigators().items():
        g.add_node(name, fn)
    g.add_node("orchestrator", orchestrator_node)
    g.add_node("risk_judge", risk_judge_node)
    for name in AGENTS:
        g.add_edge(START, name)              # first pass: all investigators in parallel
        g.add_edge(name, "orchestrator")     # every result returns to the orchestrator
    g.add_conditional_edges("orchestrator", route_after_orchestrator, AGENTS + ["risk_judge"])
    g.add_edge("risk_judge", END)
    return g.compile()


def run_scan(user_input: dict) -> dict:
    rid = new_run_id()
    emit(rid, "user", "investigators", "input", user_input)
    final = build_graph().invoke({
        "run_id": rid, "input": user_input, "evidence": [], "unavailable": [],
        "conflicts": [], "requests": {}, "loop_count": 0})
    return {"run_id": rid, "report": final["final"], "trace": read_run(rid), "state": final}