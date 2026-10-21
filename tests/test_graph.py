import tracelog
from agents import orchestrator as orch
from agents import risk_judge as judge


def test_reverification_loop(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_STUBS", "1")
    monkeypatch.setattr(tracelog, "TRACE_FILE", tmp_path / "t.jsonl")
    calls = {"n": 0}

    def fake_orch(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"status": "REVERIFY", "conflicts": ["reviews vs new domain"], "gaps": [],
                    "reverify_requests": [{"agent": "reputation", "question": "independent reviews?"}]}
        return {"status": "OK", "conflicts": [], "gaps": [], "reverify_requests": []}

    def no_llm(*a, **k):
        raise RuntimeError("no llm")

    monkeypatch.setattr(orch, "chat_json", fake_orch)
    monkeypatch.setattr(judge, "chat_json", no_llm)

    from graph import run_scan
    res = run_scan({"url": "https://cozy-flats-pune.xyz", "category": "rental"})

    assert calls["n"] == 2                       # orchestrator ran twice: before and after re-verification
    assert res["state"]["loop_count"] == 1
    assert res["report"]["risk_level"] == "HIGH"
    assert "reverify_request" in [e["type"] for e in res["trace"]]