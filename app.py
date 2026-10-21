import json
import re

import pandas as pd
import streamlit as st

from graph import run_scan

st.set_page_config(page_title="ScamShield AI", page_icon="🛡️", layout="wide")
st.title("🛡️ ScamShield AI")
st.caption("Multi-agent trust & risk detection: agents investigate, cross-check and resolve conflicting evidence.")

CATS = ["rental", "website", "seller", "job", "offer"]
PRESETS = {
    "Custom": {"url": "", "category": "website", "description": "", "claimed_price": 0.0, "location": ""},
    "Suspicious rental (example)": {"url": "https://cozy-flats-pune.xyz", "category": "rental",
        "description": "2BHK flat for rent in Kothrud Pune, pay advance via UPI to book", "claimed_price": 9000.0,
        "location": "Pune"},
    "Established site (example)": {"url": "https://www.irctc.co.in", "category": "website",
        "description": "Indian railways ticket booking website", "claimed_price": 0.0, "location": ""},
}


def normalize_url(u: str) -> str | None:
    u = u.strip()
    if not u:
        return None
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    return u if re.match(r"^https?://[^\s/]+\.[^\s/]+", u) else None


preset = st.sidebar.selectbox("Load an example", list(PRESETS))
p = PRESETS[preset]
with st.form("scan"):
    url = st.text_input("Website / listing URL", p["url"], key=f"url_{preset}")
    c1, c2 = st.columns(2)
    category = c1.selectbox("Category", CATS, index=CATS.index(p["category"]), key=f"cat_{preset}")
    price = c2.number_input("Claimed price (0 = none)", min_value=0.0, value=p["claimed_price"], key=f"pr_{preset}")
    desc = st.text_area("Description of the offer", p["description"], key=f"d_{preset}")
    loc = st.text_input("Location (optional)", p["location"], key=f"l_{preset}")
    go = st.form_submit_button("🔍 Investigate", type="primary")

if go:
    clean = normalize_url(url)
    if not clean:
        st.error("Please enter a valid URL, for example https://example.com")
        st.stop()
    user_input = {"url": clean, "category": category, "description": desc,
                  "claimed_price": price or None, "location": loc}
    try:
        with st.spinner("Agents are investigating, cross-checking and resolving conflicts..."):
            res = run_scan(user_input)
    except Exception as e:
        st.error(f"The investigation failed: {e}")
        st.stop()

    rep, trace = res["report"], res["trace"]
    a, b = st.columns([1, 2])
    a.metric("Trust Score", f"{rep['trust_score']}/100")
    level = rep["risk_level"]
    {"HIGH": b.error, "MEDIUM": b.warning, "LOW": b.success, "INCONCLUSIVE": b.info}[level](
        f"**Risk level: {level}**\n\n{rep['summary']}")
    st.subheader("Recommended action")
    st.info(rep["recommended_action"])

    st.subheader("Evidence")
    df = pd.DataFrame(rep["evidence"])
    if not df.empty:
        st.dataframe(df[["agent", "signal", "finding", "severity", "confidence", "source_reliability",
                         "pass_no", "source"]], use_container_width=True)
    if rep["conflicts_resolved"]:
        st.subheader("Conflicts detected and resolved")
        for c in rep["conflicts_resolved"]:
            st.markdown(f"- **Conflict:** {c['conflict']}\n  - **Resolution:** {c['resolution']}")
    if rep["limitations"]:
        st.subheader("Limitations")
        for l in rep["limitations"]:
            st.markdown(f"- {l}")

    st.subheader("Agent timeline (execution trace)")
    for e in trace:
        with st.expander(f"{e['from']} → {e['to']} · {e['type']}"):
            st.json(e["content"])
    st.download_button("⬇️ Download trace (JSONL)", "\n".join(json.dumps(e) for e in trace),
                       file_name=f"trace_{res['run_id']}.jsonl")
    st.download_button("⬇️ Download report (JSON)", json.dumps(rep, indent=2), file_name="report.json")