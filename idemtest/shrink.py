"""Failure shrinking: remove steps / lower concurrency while the SAME invariant still fails."""
import asyncio
from .checker import check_trace
from .executor import make_client, run_scenario
from .models import Scenario


async def violates(app_factory, scenario: Scenario, invariant: str) -> bool:
    app = app_factory()                       # fresh state every run
    async with make_client(app) as client:
        trace = await run_scenario(client, scenario)
    return any(x.invariant == invariant for x in check_trace(trace))


async def shrink(app_factory, scenario: Scenario, invariant: str) -> Scenario:
    cur = scenario.model_copy(deep=True)
    changed = True
    while changed:
        changed = False
        for i in range(len(cur.steps)):                 # try deleting each step
            if len(cur.steps) == 1:
                break
            cand = cur.model_copy(deep=True)
            del cand.steps[i]
            if await violates(app_factory, cand, invariant):
                cur, changed = cand, True
                break
        if changed:
            continue
        for i, s in enumerate(cur.steps):               # try lowering concurrency
            if s.repeat > 2:
                cand = cur.model_copy(deep=True)
                cand.steps[i].repeat = s.repeat - 1
                if await violates(app_factory, cand, invariant):
                    cur, changed = cand, True
                    break
    return cur
