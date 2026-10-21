"""Fake investigators that reproduce the worked example. Used for tests and offline dev (USE_STUBS=1)."""


def _ev(agent, finding, signal, sev, conf, src, rel, pass_no=1):
    return {"agent": agent, "finding": finding, "signal": signal, "severity": sev, "confidence": conf,
            "source": src, "source_reliability": rel, "pass_no": pass_no}


def web_detective_node(state):
    return {"evidence": [_ev("web_detective", "Domain registered 6 days ago", "risk", .9, .95, "rdap.org", .9)]}


def reputation_node(state):
    if (state.get("requests") or {}).get("reputation"):
        return {"evidence": [_ev("reputation", "2 independent scam-report mentions, no independent positive reviews",
                                 "risk", .7, .8, "https://reddit.com/r/scams", .8, 2)]}
    return {"evidence": [_ev("reputation", "4.8 star reviews shown on the listing site itself",
                             "trust", .6, .5, "site", .2)]}


def price_market_node(state):
    return {"evidence": [_ev("price_market", "Rent is 55% below the area median", "risk", .8, .8, "comparables", .7)]}