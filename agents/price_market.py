import re
import statistics

from agents.common import get_request, pass_no, report, safe_node
from tools.apify_tools import ToolUnavailable, google_search
from tools.llm import FAST, chat_json
from tracelog import emit

PLAN_SYSTEM = """Write ONE web search query that finds comparable prices for the item/listing described
(same type, same area). If told the previous query found too few prices, rephrase. JSON: {"query": str}"""

EXTRACT_SYSTEM = """From the search results extract prices of genuinely comparable items, in the same currency
as the claimed price. Ignore unrelated or different-currency prices. Do not invent.
JSON: {"comparables":[{"price": number, "source": url}]}"""


def _num(x):
    try:
        return float(re.sub(r"[^\d.]", "", str(x)))
    except ValueError:
        return None


def market_evidence(claimed: float, comps: list, pass_no: int = 1):
    """Pure function: compare the claimed price to comparable prices. Returns (evidence_list, deviation)."""
    prices = [p for p in (_num(c.get("price")) for c in comps if isinstance(c, dict)) if p and p > 0]
    if len(prices) < 2:
        return [], None
    med = statistics.median(prices)
    dev = (claimed - med) / med
    conf = 0.8 if len(prices) >= 4 else 0.55
    if dev <= -0.4:
        signal, sev = "risk", 0.85
    elif dev <= -0.25:
        signal, sev = "risk", 0.55
    elif dev >= 0.5:
        signal, sev = "risk", 0.3
    else:
        signal, sev = "trust", 0.4
    finding = f"Claimed price {claimed:g} is {dev:+.0%} vs market median {med:g} (n={len(prices)})"
    return [{"agent": "price_market", "finding": finding, "signal": signal, "severity": sev,
             "confidence": conf, "source": "google search comparables", "source_reliability": 0.6,
             "pass_no": pass_no}], dev


@safe_node("price_market")
def price_market_node(state):
    rid, inp, pn = state["run_id"], state["input"], pass_no(state)
    question = get_request(state, "price_market")
    claimed = _num(inp.get("claimed_price"))
    if not claimed:
        raise RuntimeError("no claimed_price supplied, so the price check is not applicable")

    comps, ok_calls, last_err = [], 0, None
    for attempt in range(2):
        user = (f"Category: {inp.get('category')}\nDescription: {inp.get('description', '')}\n"
                f"Location: {inp.get('location', '')}\nFocus: {question or 'none'}\n"
                + ("Previous query found too few prices; rephrase." if attempt else ""))
        q = chat_json(PLAN_SYSTEM, user, model=FAST).get("query") or f"{inp.get('description', '')} price"
        emit(rid, "price_market", "tools", "tool_call", {"tool": "google_search", "query": q})
        try:
            results = google_search(str(q))
            ok_calls += 1
        except ToolUnavailable as e:
            last_err = e
            continue
        if results:
            listing = "\n".join(f"{r['url']} | {r['title']} | {r['snippet']}" for r in results)
            out = chat_json(EXTRACT_SYSTEM, f"Claimed price: {claimed}\n\nRESULTS:\n{listing}", model=FAST)
            comps += [c for c in out.get("comparables", []) if isinstance(c, dict)]
        if sum(1 for c in comps if _num(c.get("price"))) >= 3:
            break
    if ok_calls == 0:
        raise last_err or RuntimeError("no search was possible")

    evidence, _ = market_evidence(claimed, comps, pn)
    if not evidence:
        raise RuntimeError("not enough comparable prices found online to judge the claimed price")
    report(rid, "price_market", evidence)
    return {"evidence": evidence}