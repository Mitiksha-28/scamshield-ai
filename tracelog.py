import json
import os
import threading
import time
import uuid
from pathlib import Path

TRACE_FILE = Path(os.getenv("TRACE_FILE", "traces/trace.jsonl"))
_lock = threading.Lock()


def new_run_id() -> str:
    return uuid.uuid4().hex[:8]


def emit(run_id: str, sender: str, receiver: str, kind: str, content) -> dict:
    """Append one agent message to the trace file and return it."""
    entry = {"ts": round(time.time(), 2), "run_id": run_id, "from": sender,
             "to": receiver, "type": kind, "content": content}
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _lock, TRACE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return entry


def read_run(run_id: str) -> list[dict]:
    if not TRACE_FILE.exists():
        return []
    out = []
    for line in TRACE_FILE.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("run_id") == run_id:
            out.append(e)
    return out