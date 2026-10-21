from agents.common import domain_of, get_request, pass_no, prior_context, report, safe_node, to_evidence
from tools.apify_tools import ToolUnavailable, crawl_page
from tools.llm import FAST, chat_json
from tools.whois_tool import domain_age_days, registrable
from tracelog import emit

SYSTEM = """You analyse web page text for scam signals. Look for: urgency or pressure, requests for advance
payment (UPI, crypto, wire, gift cards), missing or fake contact details/address/phone, too-good-to-be-true
claims, missing refund policy or terms, template or poor-quality text. Also report genuine trust signals
(clear company details, policies, verifiable contacts). Use ONLY the given text; do not invent.
JSON: {"evidence":[{"finding":str,"signal":"risk"|"trust","severity":0-1,"confidence":0-1}]} (max 5 items)."""


def domain_age_evidence(days, domain):
    if days is None:
        return []
    if days < 30:
        signal, sev, text = "risk", 0.9, f"Domain {domain} was registered only {days} days ago"
    elif days < 180:
        signal, sev, text = "risk", 0.6, f"Domain {domain} is young ({days} days old)"
    elif days >= 1095:
        signal, sev, text = "trust", 0.5, f"Domain {domain} is established ({days // 365} years old)"
    else:
        return []
    return [{"finding": text, "signal": signal, "severity": sev, "confidence": 0.95,
             "source": "rdap.org", "source_reliability": 0.9}]


@safe_node("web_detective")
def web_detective_node(state):
    rid, inp, pn = state["run_id"], state["input"], pass_no(state)
    question = get_request(state, "web_detective")
    url = inp["url"]
    domain = domain_of(url)
    raw, notes = [], []

    if not question:  # deterministic checks only on the first pass (avoid double counting)
        emit(rid, "web_detective", "tools", "tool_call", {"tool": "rdap", "domain": domain})
        raw += domain_age_evidence(domain_age_days(registrable(domain)), domain)
        if not url.lower().startswith("https://"):
            raw.append({"finding": "Site is not served over HTTPS", "signal": "risk", "severity": 0.5,
                        "confidence": 0.9, "source": url, "source_reliability": 0.7})

    emit(rid, "web_detective", "tools", "tool_call", {"tool": "crawl_page", "url": url})
    page = None
    try:
        page = crawl_page(url)
    except ToolUnavailable as e:
        notes.append(f"page crawl failed: {e}")

    if page:
        user = (f"Category: {inp.get('category')}\nUser description: {inp.get('description', '')}\nURL: {url}\n"
                f"Team findings so far:\n{prior_context(state, 'web_detective')}\n"
                f"Focus question: {question or 'none'}\n\nPAGE TEXT:\n{page['text'][:4000]}")
        for r in chat_json(SYSTEM, user, model=FAST).get("evidence", []):
            if isinstance(r, dict):
                r["source_reliability"] = 0.7 if r.get("signal") == "risk" else 0.4
                r["source"] = url
                raw.append(r)

    evidence = to_evidence(raw, "web_detective", pn, domain)
    if not evidence:
        raise RuntimeError("; ".join(notes) or "no website evidence could be gathered")
    report(rid, "web_detective", evidence)
    result = {"evidence": evidence}
    if notes:
        result["unavailable"] = [{"agent": "web_detective", "reason": n} for n in notes]
    return result