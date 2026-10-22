"""Runs a Scenario against an API and records a trace. No judging happens here."""
import asyncio
import re
import httpx
from .models import Scenario, Step


def make_client(app) -> httpx.AsyncClient:
    """In-process client: talks to the FastAPI app directly, no server needed."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _fill(text: str, variables: dict) -> str:
    # unresolved {var} stays as-is (the API will then answer 404)
    return re.sub(r"\{(\w+)\}", lambda m: str(variables.get(m.group(1), m.group(0))), text)


async def _send(client: httpx.AsyncClient, step_idx: int, step: Step, variables: dict) -> dict:
    path = _fill(step.path, variables)
    resp = await client.request(step.method.upper(), path, json=step.body, headers=step.headers)
    try:
        data = resp.json()
    except Exception:
        data = None
    return {"step": step_idx, "method": step.method.upper(), "path": path,
            "headers": step.headers, "body": step.body,
            "status": resp.status_code, "json": data}


async def run_scenario(client: httpx.AsyncClient, scenario: Scenario) -> list[dict]:
    variables: dict = {}
    trace: list[dict] = []
    for i, step in enumerate(scenario.steps):
        results = await asyncio.gather(*[_send(client, i, step, variables) for _ in range(step.repeat)])
        trace.extend(results)
        if step.save_as:
            for r in results:
                if 200 <= r["status"] < 300 and isinstance(r["json"], dict) and "id" in r["json"]:
                    variables[step.save_as] = r["json"]["id"]
                    break
    return trace
