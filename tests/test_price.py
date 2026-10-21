from agents.price_market import market_evidence

COMPS = [{"price": "₹25,000"}, {"price": 26000}, {"price": 24000}, {"price": 27000}]


def test_big_discount_is_risk():
    ev, dev = market_evidence(12000, COMPS)
    assert ev[0]["signal"] == "risk" and ev[0]["severity"] == 0.85 and dev < -0.4


def test_fair_price_is_trust():
    ev, _ = market_evidence(25000, COMPS)
    assert ev[0]["signal"] == "trust"


def test_too_few_comparables():
    assert market_evidence(10000, [{"price": 20000}]) == ([], None)