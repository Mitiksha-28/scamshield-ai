from agents.common import domain_of, get_request, pass_no, prior_context, report, safe_node, to_evidence
from tools.apify_tools import ToolUnavailable, google_search
from tools.llm import FAST, chat_json
from tracelog import emit

PLAN_SYSTEM = """You plan web searches to check the reputation of an online entity. Return up to 3 short search
queries covering scam/fraud complaints and independent reviews. If a focus question is given, tailor the queries
to it. If told that earlier queries returned nothing, rephrase with different wording.
JSON: {"queries":[str]}"""

EXTRACT_SYSTEM = """From the search results, judge the reputation of the entity. Use signal "risk" for scam
reports/complaints and "trust" for credible independent positive reviews. "source" MUST be the URL of the result
that supports the finding. Ignore results unrelated to this entity. Do not invent anything; if nothing is
relevant return an empty list.
JSON: {"evidence":[{"finding":str,"signal":"risk"|"trust","severity":0-1,"confidence":0-1,"source":url}]} (max 5)."""


def _plan(inp, name, question, ctx, note=""):
    user = (f"Entity: {name}\nURL: {inp['url']}\nCategory: {inp.get('category')}\n"
            f"Description: {inp.get('description', '')}\nFocus question: {question or 'none'}\n"
            f"Team findings so far:\n{ctx}\n{note}")
    qs = [str(q) for q in chat_json(PLAN_SYSTEM, user, model=FAST).get("queries", []) if str(q).strip()][:3]
    return qs or [f"{name} scam", f"{name} reviews complaints"]


@safe_node("reputation")
def reputation_node(state):
    rid, inp, pn = state["run_id"], state["input"], pass_no(state)
    question = get_request(state, "reputation")
    domain = domain_of(inp["url"])
    name = inp.get("name") or domain
    ctx = prior_context(state, "reputation")

    queries = _plan(inp, name, question, ctx)
    results, ok_calls, last_err = [], 0, None
    for attempt in range(2):                       # agent rephrases itself if nothing comes back
        for q in queries:
            emit(rid, "reputation", "tools", "tool_call", {"tool": "google_search", "query": q})
            try:
                results += google_search(q)
                ok_calls += 1
            except ToolUnavailable as e:
                last_err = e
        if results:
            break
        if attempt == 0 and ok_calls:
            queries = _plan(inp, name, question, ctx, "Previous queries returned nothing. Rephrase.")
    if ok_calls == 0:
        raise last_err or RuntimeError("no search was possible")

    unique = list({r["url"]: r for r in results}.values())[:12]
    if not unique:
        raw = [{"finding": f"No independent web presence found for {name}", "signal": "risk", "severity": 0.4,
                "confidence": 0.5, "source": "google search", "source_reliability": 0.6}]
    else:
        listing = "\n".join(f"[{i}] {r['url']} | {r['title']} | {r['snippet']}" for i, r in enumerate(unique))
        user = (f"Entity: {name} ({domain})\nFocus question: {question or 'none'}\n"
                f"Team findings so far:\n{ctx}\n\nSEARCH RESULTS:\n{listing}")
        raw = chat_json(EXTRACT_SYSTEM, user, model=FAST).get("evidence", [])

    evidence = to_evidence([r for r in raw if isinstance(r, dict)], "reputation", pn, domain)
    if not evidence:
        evidence = to_evidence([{"finding": f"Searches returned nothing relevant about {name}", "signal": "risk",
                                 "severity": 0.3, "confidence": 0.4, "source": "google search",
                                 "source_reliability": 0.6}], "reputation", pn, domain)
    report(rid, "reputation", evidence)
    return {"evidence": evidence}