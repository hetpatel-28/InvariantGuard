"""Turns an OpenAPI spec (+ optionally retrieved invariants) into validated Scenarios."""
import json
import re
from pydantic import ValidationError
from .llm import generate
from .models import Scenario, Step
from .retriever import Retriever

FORMAT_RULES = """
Return ONLY a JSON object: {"scenarios": [ ... ]}. Each scenario:
{"name": str, "description": str, "steps": [ {"method": "GET|POST", "path": str,
  "body": object|null, "headers": object, "save_as": str|null, "repeat": int} ]}
Rules:
- A step with "save_as": "p" stores the "id" of its response; later paths can use it as /payments/{p}/refund.
- "repeat": N sends that step N times CONCURRENTLY (use it to test race conditions).
- Use header "Idempotency-Key" to test retries. Use ids like pay_missing to test unknown payments.
- Payments are created with POST /payments body {"amount": <int>, "currency": "INR"}.
- Max 8 steps per scenario. Produce 10 to 14 diverse scenarios that try to BREAK the rules.
"""


def endpoints_from_openapi(spec: dict) -> list[str]:
    out = []
    for path, methods in spec.get("paths", {}).items():
        for m, info in methods.items():
            out.append(f"{m.upper()} {path} - {info.get('summary', '')}")
    return out


def build_prompt(endpoints: list[str], invariants: list[str] | None) -> str:
    p = "You are a QA engineer testing a payments REST API.\nEndpoints:\n" + "\n".join(f"- {e}" for e in endpoints)
    if invariants:
        p += "\n\nBusiness rules (invariants) the API must always satisfy:\n" + "\n".join(f"- {i}" for i in invariants)
        p += "\n\nDesign scenarios that try to violate these rules."
    else:
        p += "\n\nDesign edge-case test scenarios for this API."
    return p + "\n" + FORMAT_RULES


def parse_scenarios(text: str) -> tuple[list[Scenario], int]:
    """Validate with Pydantic; drop anything malformed. Returns (valid, dropped_count)."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return [], 1
    items = raw.get("scenarios", []) if isinstance(raw, dict) else raw
    good, dropped = [], 0
    for it in items:
        try:
            good.append(Scenario.model_validate(it))
        except ValidationError:
            dropped += 1
    return good, dropped


def generate_scenarios(spec: dict, use_rag: bool, provider: str | None = None, retries: int = 1):
    endpoints = endpoints_from_openapi(spec)
    invariants = None
    if use_rag:
        r = Retriever()
        seen: list[str] = []
        for e in endpoints:                       # retrieve rules relevant to each endpoint
            for doc in r.search(e, k=5):
                if doc not in seen:
                    seen.append(doc)
        invariants = seen
    prompt = build_prompt(endpoints, invariants)
    for _ in range(retries + 1):                  # one automatic retry on unusable output
        scenarios, dropped = parse_scenarios(generate(prompt, provider))
        if scenarios:
            return scenarios, dropped
    return [], dropped


def baseline_scenarios() -> list[Scenario]:
    """Naive non-LLM template generator: one happy path and one bad input per endpoint.
    Used as a comparison baseline."""
    S = Step
    return [
        Scenario(name="create valid", steps=[S(method="POST", path="/payments", body={"amount": 100})]),
        Scenario(name="create negative", steps=[S(method="POST", path="/payments", body={"amount": -5})]),
        Scenario(name="create+capture", steps=[S(method="POST", path="/payments", body={"amount": 100}, save_as="p"),
                                               S(method="POST", path="/payments/{p}/capture")]),
        Scenario(name="create+capture+partial refund", steps=[
            S(method="POST", path="/payments", body={"amount": 100}, save_as="p"),
            S(method="POST", path="/payments/{p}/capture"),
            S(method="POST", path="/payments/{p}/refund", body={"amount": 50})]),
        Scenario(name="get unknown", steps=[S(method="GET", path="/payments/pay_missing")]),
    ]
