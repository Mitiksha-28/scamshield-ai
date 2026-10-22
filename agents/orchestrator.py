from state import AGENTS, MAX_LOOPS
from tools.llm import chat_json, STRONG
from tracelog import emit

SYSTEM = """You are the Orchestrator of a scam-detection agent team.
Agents: web_detective (website, domain age, page red flags), reputation (external reviews,
complaints, scam reports), price_market (claimed price vs market).
You receive evidence items with signal (risk/trust), severity, confidence and source_reliability.
Find CONFLICTS (e.g. positive trust evidence from a low-reliability source contradicted by serious
risk evidence) and GAPS (missing, unavailable or low-confidence areas). For each conflict or gap that
more investigation could resolve, write ONE targeted re-verification request naming one agent and a
specific question. Maximum 2 requests. If the evidence is consistent and sufficient, return status OK.
JSON format: {"status":"OK"|"REVERIFY","conflicts":[str],"gaps":[str],
"reverify_requests":[{"agent":str,"question":str}]}"""


def rule_hints(evidence: list, unavailable: list):
    """Deterministic checks used as hints for the LLM and as a fallback if it fails."""
    dead = {u["agent"] for u in unavailable}
    conflicts, gaps, reqs = [], [], {}
    weak = [e for e in evidence if e["signal"] == "trust" and e["source_reliability"] <= 0.3]
    strong = [e for e in evidence if e["signal"] == "risk" and e["severity"] >= 0.7 and e["confidence"] >= 0.7]
    if weak and strong:
        w, s = weak[0], strong[0]
        conflicts.append(
            f"Trust evidence from {w['agent']} ('{w['finding']}') comes from a low-reliability source "
            f"but contradicts high-severity risk evidence from {s['agent']} ('{s['finding']}')")
        if "reputation" not in dead:
            reqs["reputation"] = (
                f"Find independent third-party evidence (reviews, complaints, scam reports) that confirms or "
                f"contradicts: '{w['finding']}'. Context: {s['agent']} found '{s['finding']}'.")
    for a in AGENTS:
        if a in dead:
            reason = next(u["reason"] for u in unavailable if u["agent"] == a)
            gaps.append(f"{a} unavailable: {reason}")
        elif not any(e["agent"] == a for e in evidence):
            gaps.append(f"No evidence received from {a}")
    return conflicts, gaps, reqs


def _format(evidence, unavailable, conflicts, gaps):
    lines = [f"- [{e['agent']}] ({e['signal']}) {e['finding']} | severity={e['severity']:.2f} "
             f"confidence={e['confidence']:.2f} source_reliability={e['source_reliability']:.2f} "
             f"pass={e.get('pass_no', 1)}" for e in evidence]
    return ("EVIDENCE:\n" + ("\n".join(lines) or "none") +
            "\nUNAVAILABLE: " + (str(unavailable) or "none") +
            "\nRULE HINTS conflicts: " + str(conflicts) + " gaps: " + str(gaps))


def _parse_requests(decision: dict, dead: set) -> dict:
    reqs = {}
    for r in decision.get("reverify_requests", [])[:2]:
        if isinstance(r, dict) and r.get("agent") in AGENTS and r["agent"] not in dead and r.get("question"):
            reqs[r["agent"]] = str(r["question"])
    return reqs


def orchestrator_node(state):
    rid = state["run_id"]
    loops = state.get("loop_count", 0)
    evidence = state.get("evidence", [])
    unavailable = state.get("unavailable", [])
    dead = {u["agent"] for u in unavailable}
    h_conflicts, h_gaps, h_reqs = rule_hints(evidence, unavailable)

    source = "llm"
    try:
        decision = chat_json(SYSTEM, _format(evidence, unavailable, h_conflicts, h_gaps), model=STRONG)
        reqs = _parse_requests(decision, dead)
        if not reqs and h_reqs and loops == 0:   # safety net if the LLM missed an obvious conflict
            reqs, source = h_reqs, "rule_fallback"
    except Exception as e:
        emit(rid, "orchestrator", "orchestrator", "error", {"error": str(e)[:200]})
        decision = {"conflicts": h_conflicts, "gaps": h_gaps}
        reqs, source = (h_reqs if loops == 0 else {}), "rule_fallback"

    if loops >= MAX_LOOPS:
        reqs = {}
    conflicts = [str(c) for c in decision.get("conflicts", [])]
    gaps = [str(g) for g in decision.get("gaps", [])]

    emit(rid, "orchestrator", "orchestrator", "decision", {
        "status": "REVERIFY" if reqs else "OK", "round": loops + 1, "decided_by": source,
        "conflicts": conflicts, "gaps": gaps})
    for agent, q in reqs.items():
        emit(rid, "orchestrator", agent, "reverify_request", {"question": q})
    if not reqs:
        emit(rid, "orchestrator", "risk_judge", "handoff", {"evidence_count": len(evidence)})

    out = {"requests": reqs, "conflicts": [{"round": loops + 1, "text": c} for c in conflicts]}
    if reqs:
        out["loop_count"] = loops + 1
    return out