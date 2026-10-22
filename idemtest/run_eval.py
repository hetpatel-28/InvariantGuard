"""Evaluation: run each scenario set against the CLEAN api and every BUGGY api.

  python -m idemtest.run_eval --modes baseline llm_rag llm_norag --provider gemini
"""
import argparse
import asyncio
import json
from pathlib import Path

from mock_api.app import ALL_BUGS, create_app
from .checker import check_trace
from .executor import make_client, run_scenario
from .generator import baseline_scenarios, generate_scenarios
from .models import Scenario
from .shrink import shrink

OUT = Path(__file__).resolve().parent.parent / "out"


async def run_all(bugs: set, scenarios: list[Scenario]):
    """Returns {invariant: scenario_that_caught_it} for one API variant."""
    caught: dict = {}
    for sc in scenarios:
        app = create_app(bugs)                    # fresh state per scenario
        async with make_client(app) as client:
            trace = await run_scenario(client, sc)
        for v in check_trace(trace):
            caught.setdefault(v.invariant, sc)
    return caught


def get_scenarios(mode: str, provider, regen: bool):
    cache = OUT / f"scenarios_{mode}.json"
    if mode != "baseline" and cache.exists() and not regen:
        return [Scenario.model_validate(x) for x in json.loads(cache.read_text())], 0
    if mode == "baseline":
        return baseline_scenarios(), 0
    spec = create_app().openapi()
    scs, dropped = generate_scenarios(spec, use_rag=(mode == "llm_rag"), provider=provider)
    OUT.mkdir(exist_ok=True)
    cache.write_text(json.dumps([s.model_dump() for s in scs], indent=2))
    return scs, dropped


async def evaluate(mode: str, provider, regen: bool, do_shrink: bool):
    scenarios, dropped = get_scenarios(mode, provider, regen)
    rows, repros = [], []
    clean = await run_all(set(), scenarios)
    for bug in ALL_BUGS:
        caught = await run_all({bug}, scenarios)
        detected = bool(caught)
        by = sorted(caught)
        rows.append({"bug": bug, "detected": detected, "invariants": by})
        if detected and do_shrink:
            inv = by[0]
            small = await shrink(lambda b=bug: create_app({b}), caught[inv], inv)
            repros.append({"bug": bug, "invariant": inv,
                           "original_steps": len(caught[inv].steps),
                           "minimal": small.model_dump()})
    found = sum(r["detected"] for r in rows)
    return {"mode": mode, "n_scenarios": len(scenarios), "dropped_invalid": dropped,
            "bugs_found": found, "bugs_total": len(ALL_BUGS),
            "false_positive_invariants_on_clean": sorted(clean), "rows": rows, "repros": repros}


def write_outputs(results: list[dict]):
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    lines = ["# InvariantGuard results\n", "| mode | scenarios | invalid dropped | bugs found | false positives on clean API |",
             "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['mode']} | {r['n_scenarios']} | {r['dropped_invalid']} | "
                     f"{r['bugs_found']}/{r['bugs_total']} | {len(r['false_positive_invariants_on_clean'])} |")
    lines.append("\n## Per-bug detection\n")
    lines.append("| bug | " + " | ".join(r["mode"] for r in results) + " |")
    lines.append("|---|" + "---|" * len(results))
    for i, bug in enumerate(ALL_BUGS):
        lines.append(f"| {bug} | " + " | ".join("yes" if r["rows"][i]["detected"] else "no" for r in results) + " |")
    for r in results:
        if r["repros"]:
            lines.append(f"\n## Minimal reproductions ({r['mode']})\n")
            for rp in r["repros"]:
                steps = "; ".join(
                    f"{s['method']} {s['path']}" + (f" x{s['repeat']} concurrently" if s["repeat"] > 1 else "")
                    + (f" body={s['body']}" if s["body"] else "") for s in rp["minimal"]["steps"])
                lines.append(f"- **{rp['bug']}** violates `{rp['invariant']}`: {rp['original_steps']} steps "
                             f"shrunk to {len(rp['minimal']['steps'])}: {steps}")
    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["baseline", "llm_rag", "llm_norag"],
                    choices=["baseline", "llm_rag", "llm_norag"])
    ap.add_argument("--provider", default=None, help="gemini | groq | mock (default: $LLM_PROVIDER or mock)")
    ap.add_argument("--regen", action="store_true", help="ask the LLM again instead of using cached scenarios")
    ap.add_argument("--no-shrink", action="store_true")
    a = ap.parse_args()
    results = [asyncio.run(evaluate(m, a.provider, a.regen, not a.no_shrink)) for m in a.modes]
    write_outputs(results)


if __name__ == "__main__":
    main()
