import os
import re

import requests
from apify_client import ApifyClient
from dotenv import load_dotenv

from tools import cache

load_dotenv()


class ToolUnavailable(Exception):
    """Raised when a tool cannot produce data. Agents turn this into a gap instead of crashing."""


def _client() -> ApifyClient:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise ToolUnavailable("APIFY_TOKEN is not set")
    return ApifyClient(token)


def google_search(query: str, max_results: int = 8) -> list[dict]:
    hit = cache.get("search", query)
    if hit is not None:
        return hit
    try:
        c = _client()
        run = c.actor("apify/google-search-scraper").call(
            run_input={"queries": query, "resultsPerPage": max_results, "maxPagesPerQuery": 1},
            timeout_secs=90)
        items = c.dataset(run["defaultDatasetId"]).list_items().items
    except ToolUnavailable:
        raise
    except Exception as e:
        raise ToolUnavailable(f"Apify search failed: {e}")
    results = []
    for it in items:
        for r in it.get("organicResults", []):
            results.append({"title": r.get("title", ""), "url": r.get("url", ""),
                            "snippet": r.get("description", "")})
    results = results[:max_results]
    if results:
        cache.put("search", query, results)
    return results


def _plain_fetch(url: str) -> str:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 ScamShieldBot"})
        r.raise_for_status()
    except Exception as e:
        raise ToolUnavailable(f"Could not fetch page: {e}")
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", r.text)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


def crawl_page(url: str, max_chars: int = 6000) -> dict:
    hit = cache.get("crawl", url)
    if hit is not None:
        return hit
    text, via = "", "apify"
    try:
        c = _client()
        run = c.actor("apify/website-content-crawler").call(
            run_input={"startUrls": [{"url": url}], "maxCrawlPages": 2, "crawlerType": "cheerio"},
            timeout_secs=120)
        items = c.dataset(run["defaultDatasetId"]).list_items().items
        text = "\n".join(i.get("text", "") for i in items)
    except Exception:
        text = ""
    if not text.strip():
        text, via = _plain_fetch(url), "requests"
    out = {"url": url, "text": text[:max_chars], "via": via}
    cache.put("crawl", url, out)
    return out