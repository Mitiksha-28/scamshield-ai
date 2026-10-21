import json
import os
import time

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

FAST = os.getenv("FAST_MODEL", "llama-3.1-8b-instant")
STRONG = os.getenv("STRONG_MODEL", "llama-3.3-70b-versatile")
_client = None


def _get():
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = Groq(api_key=key)
    return _client


def chat_json(system: str, user: str, model: str = FAST, retries: int = 3) -> dict:
    """Call the LLM in JSON mode and return the parsed dict."""
    client = _get()
    last = None
    for i in range(retries):
        try:
            r = client.chat.completions.create(
                model=model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system + "\nRespond with a single valid JSON object only."},
                    {"role": "user", "content": user},
                ],
            )
            return json.loads(r.choices[0].message.content)
        except Exception as e:  # rate limit, bad JSON, network
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"LLM call failed after {retries} tries: {last}")