import tracelog
from agents import orchestrator as orch

WEAK = {"agent": "reputation", "finding": "4.8 star reviews on the site itself", "signal": "trust",
        "severity": 0.6, "confidence": 0.5, "source": "site", "source_reliability": 0.2, "pass_no": 1}
STRONG = {"agent": "web_detective", "finding": "Domain 6 days old", "signal": "risk",
          "severity": 0.9, "confidence": 0.95, "source": "rdap.org", "source_reliability": 0.9, "pass_no": 1}
REQ = {"status": "REVERIFY", "conflicts": ["reviews vs new domain"], "gaps": [],
       "reverify_requests": [{"agent": "reputation", "question": "find independent reviews"}]}


def state(**kw):
    s = {"run_id": "t", "input": {}, "evidence": [WEAK, STRONG], "unavailable": [], "loop_count": 0}
    s.update(kw)
    return s


def setup(monkeypatch, tmp_path, llm):
    monkeypatch.setattr(tracelog, "TRACE_FILE", tmp_path / "t.jsonl")
    monkeypatch.setattr(orch, "chat_json", llm)


def test_rule_hints_detect_conflict():
    c, g, r = orch.rule_hints([WEAK, STRONG], [])
    assert c and "reputation" in r


def test_requests_reverification(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, lambda *a, **k: REQ)
    out = orch.orchestrator_node(state())
    assert out["requests"] == {"reputation": "find independent reviews"}
    assert out["loop_count"] == 1


def test_loop_cap(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, lambda *a, **k: REQ)
    out = orch.orchestrator_node(state(loop_count=2))
    assert out["requests"] == {} and "loop_count" not in out


def test_dead_agent_not_requested(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, lambda *a, **k: REQ)
    out = orch.orchestrator_node(state(unavailable=[{"agent": "reputation", "reason": "down"}]))
    assert out["requests"] == {}


def test_llm_failure_falls_back_to_rules(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("llm down")
    setup(monkeypatch, tmp_path, boom)
    out = orch.orchestrator_node(state())
    assert "reputation" in out["requests"]