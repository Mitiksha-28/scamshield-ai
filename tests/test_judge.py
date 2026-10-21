import tracelog
from agents import risk_judge as judge
from agents.risk_judge import compute
from state import Evidence


def ev(agent, signal, sev, conf, rel, finding="f"):
    return Evidence(agent=agent, finding=finding, signal=signal, severity=sev, confidence=conf,
                    source_reliability=rel)


SCAM = [ev("web_detective", "risk", .9, .95, .9, "a"), ev("price_market", "risk", .8, .8, .7, "b"),
        ev("reputation", "risk", .7, .8, .8, "c"), ev("reputation", "trust", .6, .5, .2, "d")]


def test_scam_is_high_risk():
    score, level, _, _ = compute(SCAM)
    assert level == "HIGH" and score < 35


def test_benign_is_low_risk():
    score, level, _, _ = compute([ev("web_detective", "trust", .5, .95, .9, "a"),
                                  ev("reputation", "trust", .6, .8, .8, "b"),
                                  ev("price_market", "risk", .1, .5, .5, "c")])
    assert level == "LOW" and score >= 65


def test_low_reliability_counts_less():
    weak = compute([ev("r", "trust", .6, .5, .2)])[3]
    strong = compute([ev("r", "trust", .6, .5, .9)])[3]
    assert weak < strong


def test_no_evidence_is_inconclusive():
    assert compute([]) == (50, "INCONCLUSIVE", 0, 0)


def test_duplicates_not_double_counted():
    assert compute(SCAM + SCAM[:1]) == compute(SCAM)


def test_node_falls_back_when_llm_fails(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(tracelog, "TRACE_FILE", tmp_path / "t.jsonl")
    monkeypatch.setattr(judge, "chat_json", boom)
    out = judge.risk_judge_node({"run_id": "t", "evidence": [e.model_dump() for e in SCAM],
                                 "conflicts": [], "unavailable": [], "loop_count": 0})
    assert out["final"]["risk_level"] == "HIGH" and out["final"]["recommended_action"]