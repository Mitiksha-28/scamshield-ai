# 🛡️ ScamShield AI

**Multi-agent trust & risk detection.** Paste a suspicious link or listing and a team of AI agents investigates it, cross-checks and resolves conflicting evidence, then returns a Trust Score (0-100), a risk level, a plain-language explanation and a recommended action.

**Live demo:** https://scamshield-ai-nefp4ux8ud8ngomjnbp57j.streamlit.app/

---

## Why

Scam sites and fake listings (rentals, jobs, shops, "offers") are easy to build and hard to check by hand. Single-signal tools are easy to fool because scam sites often display fake five-star reviews about themselves. ScamShield AI weighs **who said what**: a site vouching for itself counts for far less than a government source or an independent review platform.

## How it works

```
                 User (Streamlit UI)
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
 web_detective       reputation        price_market      (run in parallel)
      └──────────────────┼──────────────────┘
                         ▼
                   orchestrator ──── REVERIFY (max 2 rounds) ──► back to the named agent(s)
                         │ OK
                         ▼
                    risk_judge ──► FinalReport + execution trace
```

| Agent | What it does |
|---|---|
| `web_detective` | Domain age (RDAP), HTTPS check, LLM analysis of crawled page text for urgency, advance-payment requests, missing contacts or refund policy |
| `reputation` | Plans its own searches, extracts independent scam reports and reviews, rephrases queries if nothing is found |
| `price_market` | Finds comparable prices and compares the claimed price to the market median (skipped if no price is given) |
| `orchestrator` | Detects conflicts and gaps in the shared evidence and sends targeted re-verification requests (LLM, with deterministic rule fallback) |
| `risk_judge` | Computes the weighted score and writes the explanation of how conflicts were reconciled |

**Communication pattern:** blackboard plus orchestrated hub-and-spoke. Agents never call each other directly. They append evidence to a shared state (`state.evidence`) and report to the orchestrator, which decides whether to loop or hand off to the judge. Every message is logged to `traces/trace.jsonl`.

### Scoring

- Evidence weight = `severity × confidence × source_reliability`
- Score = `round(100 × (1 − R / (R + T + 0.3)))`, where R and T are the summed weights of risk and trust evidence
- Level: **LOW** ≥ 65, **MEDIUM** 35-64, **HIGH** < 35, **INCONCLUSIVE** if total weight < 0.15
- Source reliability: the entity vouching for itself 0.2, review/complaint sites 0.8, government/education 0.9, other 0.5

### Reliability features

- Tool or LLM failures become recorded **limitations**, never crashes
- LLM output is validated and clamped (`agents/common.py`) before it enters the state
- Bounded re-verification loop (`MAX_LOOPS = 2`)
- Evidence is de-duplicated so re-verification cannot double count
- Search, crawl and RDAP results are cached on disk

## Input

| Field | Type | Required | Notes |
|---|---|---|---|
| `url` | string | Yes | `https://` is added if missing |
| `category` | `rental` \| `website` \| `seller` \| `job` \| `offer` | Yes | |
| `description` | string | No | Describes the offer |
| `claimed_price` | number | No | 0 or empty skips the price check |
| `location` | string | No | Helps find local price comparables |

```json
{
  "url": "https://cozy-flats-pune.xyz",
  "category": "rental",
  "description": "2BHK flat for rent in Kothrud Pune, pay advance via UPI to book",
  "claimed_price": 9000.0,
  "location": "Pune"
}
```

## Output

A `FinalReport` (see `state.py`), downloadable as JSON from the UI:

`trust_score`, `risk_level`, `summary`, `recommended_action`, `evidence[]` (agent, finding, signal, severity, confidence, source, source_reliability, pass_no), `conflicts_resolved[]`, `limitations[]`, `risk_weight`, `trust_weight`.

The **execution trace** (JSON Lines) has one message per line with the keys `ts`, `run_id`, `from`, `to`, `type`, `content`. Message types: `input`, `tool_call`, `evidence`, `decision`, `reverify_request`, `handoff`, `error`, `final_report`.

## Tech stack

Python · [LangGraph](https://github.com/langchain-ai/langgraph) · Pydantic v2 · Groq (`openai/gpt-oss-20b` for fast agent tasks, `openai/gpt-oss-120b` for orchestration and judgement) · Apify (Google search and website crawler) · RDAP · Streamlit · pytest

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/Mitiksha-28/scamshield-ai.git
cd scamshield-ai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API keys

You need a [Groq](https://console.groq.com) API key and an [Apify](https://apify.com) token.

```bash
cp .env.example .env
```

```env
GROQ_API_KEY=your-groq-key
APIFY_TOKEN=your-apify-token
FAST_MODEL=openai/gpt-oss-20b
STRONG_MODEL=openai/gpt-oss-120b
USE_STUBS=0
```

### 3. Run

```bash
streamlit run app.py
```

Open http://localhost:8501, pick an example from the sidebar (or enter your own URL) and click **Investigate**.

### Offline / no-keys mode

Set `USE_STUBS=1` to replace the three investigators with deterministic stub agents that reproduce a worked example (new domain + self-hosted fake reviews + below-market rent → re-verification → HIGH risk). Useful for development and tests. Note that the orchestrator and judge still use the LLM unless it is unavailable, in which case they fall back to their rule-based logic.

### Deploy on Streamlit Community Cloud

1. Push this repo to GitHub and create an app pointing at `app.py`.
2. In **Settings → Secrets**, add:
   ```toml
   GROQ_API_KEY = "your-groq-key"
   APIFY_TOKEN = "your-apify-token"
   ```

## Tests

```bash
pytest
```

Covers state and evidence models, helper functions, price logic, the risk judge, the orchestrator and the full graph re-verification loop (using stub agents).

## Project structure

```
app.py                 Streamlit UI (form, report, evidence table, trace viewer)
graph.py               LangGraph definition and run_scan() entry point
state.py               Pydantic models (Evidence, FinalReport) and shared ScamState
tracelog.py            JSONL execution-trace writer/reader
agents/
  web_detective.py     Domain age, HTTPS, page analysis
  reputation.py        Reviews and scam-report search
  price_market.py      Claimed price vs market median
  orchestrator.py      Conflict/gap detection, re-verification requests
  risk_judge.py        Scoring and final report
  common.py            Evidence validation, source reliability, safe_node wrapper
  stubs.py             Deterministic agents for tests and offline use
tools/
  apify_tools.py       Google search and page crawl (with requests fallback)
  whois_tool.py        RDAP domain-age lookup
  llm.py               Groq JSON-mode client with retries
  cache.py             On-disk cache
tests/                 pytest suite
```

## Example use cases to try

| Case | URL | Category | Claimed price | Expectation |
|---|---|---|---|---|
| Established site | `https://www.irctc.co.in` | website | 0 | Mostly trust signals; price check skipped |
| Suspicious rental | `https://cozy-flats-pune.xyz` | rental | 9000 | Young or unreachable domain, below-market price → higher risk |

## Limitations

- Depends on third-party services (Groq, Apify, RDAP). Free-tier limits can lead to INCONCLUSIVE results.
- Some legitimate sites block crawlers, which reduces on-page evidence.
- Price checking needs a claimed price and findable comparables.
- Source reliability is heuristic and domain-based.
- The output is risk guidance, **not proof of fraud**. Always verify independently before paying.

## If you've been scammed (India)

Report at [cybercrime.gov.in](https://cybercrime.gov.in) or call **1930**.