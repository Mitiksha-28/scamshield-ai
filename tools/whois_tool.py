import datetime as dt

import requests

from tools import cache


def registrable(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "ac") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def domain_age_days(domain: str):
    """Age of the domain in days, or None if it cannot be determined."""
    hit = cache.get("rdap", domain)
    if hit is not None:
        return hit.get("days")
    try:
        r = requests.get(f"https://rdap.org/domain/{domain}", timeout=10)
        r.raise_for_status()
        for ev in r.json().get("events", []):
            if ev.get("eventAction") == "registration":
                created = dt.datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                days = (dt.datetime.now(dt.timezone.utc) - created).days
                cache.put("rdap", domain, {"days": days})
                return days
    except Exception:
        return None
    return None