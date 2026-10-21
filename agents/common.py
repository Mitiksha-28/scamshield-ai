import functools
from urllib.parse import urlparse

from tracelog import emit

REVIEW_SITES = ("trustpilot", "reddit", "scamadviser", "quora", "consumercomplaints", "mouthshut",
                "ripoffreport", "sitejabber", "scamwatch", "cybercrime.gov.in", "bbb.org")


def domain_of(url: str) -> str:
    host = urlparse(url if "//" in url else "//" + url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def source_reliability(source_url: str, entity_domain: str | None) -> float:
    d = domain_of(source_url)
    if entity_domain and entity_domain in d:
        return 0.2                                   # the entity vouching for itself
    if any(k in d for k in REVIEW_SITES):
        return 0.8
    if d.endswith((".gov", ".gov.in", ".edu", ".ac.in")) or ".gov." in d:
        return 0.9
    return 0.5


def _clamp(x, default=0.5) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return default


def to_evidence(raw_items, agent: str, pass_no: int, entity_domain: str | None = None) -> list[dict]:
    """Validate/clamp raw LLM or tool output into Evidence dicts. Bad items are dropped."""
    out = []
    for r in raw_items or []:
        try:
            src = str(r.get("source", "n/a"))
            if "source_reliability" in r:
                rel = _clamp(r["source_reliability"])
            elif src.startswith(("http://", "https://", "www.")):
                rel = source_reliability(src, entity_domain)
            else:
                rel = 0.5
            out.append({"agent": agent, "finding": str(r["finding"])[:300],
                        "signal": r["signal"] if r.get("signal") in ("risk", "trust") else "risk",
                        "severity": _clamp(r.get("severity")), "confidence": _clamp(r.get("confidence")),
                        "source": src, "source_reliability": rel, "pass_no": pass_no})
        except (KeyError, AttributeError, TypeError):
            continue
    return out


def pass_no(state) -> int:
    return state.get("loop_count", 0) + 1


def get_request(state, agent: str):
    return (state.get("requests") or {}).get(agent)


def prior_context(state, exclude: str | None = None, limit: int = 6) -> str:
    """Findings from other agents: the shared memory second-pass investigators can use."""
    lines = [f"- [{e['agent']}] {e['finding']} ({e['signal']})"
             for e in state.get("evidence", []) if e["agent"] != exclude][:limit]
    return "\n".join(lines) or "none yet"


def report(run_id: str, agent: str, evidence: list[dict]) -> None:
    emit(run_id, agent, "orchestrator", "evidence",
         [{k: e[k] for k in ("finding", "signal", "severity", "confidence", "source_reliability")}
          for e in evidence])


def safe_node(name: str):
    """A tool or LLM failure becomes a recorded gap (unavailable), not a crash."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(state):
            try:
                return fn(state)
            except Exception as e:
                emit(state.get("run_id", "?"), name, "orchestrator", "error", {"error": str(e)[:300]})
                return {"evidence": [], "unavailable": [{"agent": name, "reason": str(e)[:200]}]}
        return wrapper
    return deco
