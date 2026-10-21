from state import ConflictResolution, Evidence, FinalReport, MAX_LOOPS
from tools.llm import chat_json, STRONG
from tracelog import emit

SYSTEM = """You are the Risk Judge of a scam-detection team. Using ONLY the evidence given, write for a
non-technical person. Explain how conflicting evidence was reconciled (low-reliability trust evidence
counts less than high-reliability risk evidence). JSON: {"summary": str (2-3 sentences),
"recommended_action": str (concrete, 1-2 sentences),
"conflicts_resolved": [{"conflict": str, "resolution": str}]}"""

ACTIONS = {
    "HIGH": "Do not pay anything or share personal/financial details. If you were already contacted or paid, "
            "report it at cybercrime.gov.in or call 1930 (India).",
    "MEDIUM": "Proceed with caution: verify independently, avoid advance payments and use traceable payment methods.",
    "LOW": "No major red flags found. Still verify details and avoid paying in advance.",
    "INCONCLUSIVE": "Not enough evidence to judge. Do not pay until the seller or site is verified independently.",
}


def dedupe(evs):
    return list({(e.agent, e.finding, e.source): e for e in evs}.values())


def compute(evs):
    """Return (trust_score, risk_level, risk_weight, trust_weight)."""
    evs = dedupe(evs)
    r = sum(e.weight for e in evs if e.signal == "risk")
    t = sum(e.weight for e in evs if e.signal == "trust")
    if r + t < 0.15:
        return 50, "INCONCLUSIVE", r, t
    score = round(100 * (1 - r / (r + t + 0.3)))
    level = "LOW" if score >= 65 else "MEDIUM" if score >= 35 else "HIGH"
    return score, level, r, t


def risk_judge_node(state):
    rid = state["run_id"]
    evs = []
    for e in state.get("evidence", []):
        try:
            evs.append(Evidence(**e))
        except Exception:
            pass
    evs = dedupe(evs)
    score, level, r, t = compute(evs)
    conflicts = list(dict.fromkeys(c["text"] for c in state.get("conflicts", [])))[:4]
    limits = [f"{u['agent']}: {u['reason']}" for u in state.get("unavailable", [])]
    if state.get("loop_count", 0) >= MAX_LOOPS:
        limits.append("Re-verification limit reached; some conflicts may remain open.")
    if len(evs) < 3:
        limits.append("Few pieces of evidence were available.")

    top = sorted(evs, key=lambda e: -e.weight)[:8]
    prompt = (f"Trust score {score}/100, risk level {level} (risk weight {r:.2f}, trust weight {t:.2f}).\n"
              "Top evidence:\n" + "\n".join(
                  f"- [{e.agent}/{e.signal}] {e.finding} (sev {e.severity}, conf {e.confidence}, "
                  f"reliability {e.source_reliability}, pass {e.pass_no})" for e in top) +
              "\nConflicts detected: " + (str(conflicts) or "none") + "\nLimitations: " + str(limits))
    try:
        out = chat_json(SYSTEM, prompt, model=STRONG)
        summary, action = str(out["summary"]), str(out["recommended_action"])
        resolved = [ConflictResolution(**c) for c in out.get("conflicts_resolved", []) if isinstance(c, dict)]
    except Exception as e:
        emit(rid, "risk_judge", "risk_judge", "error", {"error": str(e)[:200]})
        summary = f"Trust score {score}/100 ({level} risk) based on {len(evs)} pieces of weighted evidence."
        action = ACTIONS[level]
        resolved = [ConflictResolution(conflict=c, resolution="Reconciled by weighting evidence by severity, "
                    "confidence and source reliability.") for c in conflicts]

    report = FinalReport(trust_score=score, risk_level=level, summary=summary, recommended_action=action,
                         evidence=evs, conflicts_resolved=resolved, limitations=limits,
                         risk_weight=round(r, 3), trust_weight=round(t, 3))
    emit(rid, "risk_judge", "user", "final_report", report.model_dump())
    return {"final": report.model_dump()}