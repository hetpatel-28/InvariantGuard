"""One small function that calls an LLM. Swap provider with LLM_PROVIDER=gemini|groq|mock.

Keys come from environment variables (never hard-code them):
  export GEMINI_API_KEY=...   or   export GROQ_API_KEY=...
Model names change over time - override with LLM_MODEL if the default is retired.
"""
import json
import os
import time
import httpx

# Offline stand-in so you can test the plumbing without a key. NOT a real LLM:
# it returns the same scenarios whatever the prompt says, so never report mock results.
MOCK_RESPONSE = {"scenarios": [
    {"name": "negative amount", "description": "create payment with amount -50",
     "steps": [{"method": "POST", "path": "/payments", "body": {"amount": -50, "currency": "INR"}}]},
    {"name": "idempotent retry", "description": "same key twice",
     "steps": [{"method": "POST", "path": "/payments", "body": {"amount": 100}, "headers": {"Idempotency-Key": "k1"}},
               {"method": "POST", "path": "/payments", "body": {"amount": 100}, "headers": {"Idempotency-Key": "k1"}}]},
    {"name": "double capture", "description": "capture twice",
     "steps": [{"method": "POST", "path": "/payments", "body": {"amount": 100}, "save_as": "p"},
               {"method": "POST", "path": "/payments/{p}/capture"},
               {"method": "POST", "path": "/payments/{p}/capture"}]},
    {"name": "over refund sequential", "description": "refund 70 then 70 on 100",
     "steps": [{"method": "POST", "path": "/payments", "body": {"amount": 100}, "save_as": "p"},
               {"method": "POST", "path": "/payments/{p}/capture"},
               {"method": "POST", "path": "/payments/{p}/refund", "body": {"amount": 70}},
               {"method": "POST", "path": "/payments/{p}/refund", "body": {"amount": 70}}]},
    {"name": "concurrent refunds", "description": "two simultaneous 70 refunds on 100",
     "steps": [{"method": "POST", "path": "/payments", "body": {"amount": 100}, "save_as": "p"},
               {"method": "POST", "path": "/payments/{p}/capture"},
               {"method": "POST", "path": "/payments/{p}/refund", "body": {"amount": 70}, "repeat": 2}]},
    {"name": "refund before capture", "description": "refund an authorized payment",
     "steps": [{"method": "POST", "path": "/payments", "body": {"amount": 100}, "save_as": "p"},
               {"method": "POST", "path": "/payments/{p}/refund", "body": {"amount": 10}}]},
    {"name": "unknown id", "description": "get a payment that does not exist",
     "steps": [{"method": "GET", "path": "/payments/pay_missing"}]},
]}


def generate(prompt: str, provider: str | None = None) -> str:
    provider = (provider or os.getenv("LLM_PROVIDER", "mock")).lower()
    if provider == "mock":
        return json.dumps(MOCK_RESPONSE)
    if provider == "gemini":
        model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}}
        data = _post(url, headers, payload)
        return data["candidates"][0]["content"]["parts"][0]["text"]
    if provider == "groq":
        model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}
        payload = {"model": model, "temperature": 0.8,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": prompt}]}
        data = _post(url, headers, payload)
        return data["choices"][0]["message"]["content"]
    raise ValueError(f"unknown provider {provider}")


def _post(url: str, headers: dict, payload: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        r = httpx.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:   # rate limit / transient
            time.sleep(2 ** attempt * 2)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()
