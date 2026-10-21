import tracelog
from agents.common import domain_of, safe_node, source_reliability, to_evidence
from tools.whois_tool import registrable


def test_domain_of():
    assert domain_of("https://www.Shop.com/x?y=1") == "shop.com"
    assert domain_of("shop.com/path") == "shop.com"


def test_source_reliability():
    assert source_reliability("https://shop.com/reviews", "shop.com") == 0.2
    assert source_reliability("https://trustpilot.com/review/x", "shop.com") == 0.8
    assert source_reliability("https://example.org", "shop.com") == 0.5


def test_to_evidence_clamps_and_drops_bad_items():
    out = to_evidence([{"finding": "a", "signal": "trust", "severity": 5, "confidence": -1,
                        "source": "https://trustpilot.com/x"}, {"nofinding": 1}], "reputation", 1, "shop.com")
    assert len(out) == 1 and out[0]["severity"] == 1.0 and out[0]["confidence"] == 0.0
    assert out[0]["source_reliability"] == 0.8


def test_registrable():
    assert registrable("www.shop.co.in") == "shop.co.in"
    assert registrable("a.b.example.com") == "example.com"


def test_safe_node_turns_exception_into_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(tracelog, "TRACE_FILE", tmp_path / "t.jsonl")

    @safe_node("x")
    def boom(state):
        raise RuntimeError("tool down")

    out = boom({"run_id": "t"})
    assert out["evidence"] == [] and out["unavailable"][0]["agent"] == "x"