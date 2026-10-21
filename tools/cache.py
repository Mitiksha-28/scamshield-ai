import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = Path(os.getenv("CACHE_DIR", "cache"))


def _path(ns: str, key: str) -> Path:
    return CACHE_DIR / f"{ns}-{hashlib.sha1(key.encode()).hexdigest()}.json"


def get(ns: str, key: str):
    p = _path(ns, key)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def put(ns: str, key: str, value) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(ns, key).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")