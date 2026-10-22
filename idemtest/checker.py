"""Deterministic invariant checker. This is the ONLY place that decides pass/fail.
The LLM never sees or judges results."""
import re
from collections import defaultdict
from .models import Violation

PID = re.compile(r"^/payments/([^/]+)(?:/(capture|refund))?$")


def _ok(e):  # 2xx
    return 200 <= e["status"] < 300


def check_trace(trace: list[dict]) -> list[Violation]:
    v: list[Violation] = []
    created: dict = {}                      # id -> amount (from successful creates)
    for e in trace:
        if e["method"] == "POST" and e["path"] == "/payments" and _ok(e) and isinstance(e["json"], dict) \
                and "id" in e["json"]:
            created[e["json"]["id"]] = e["json"].get("amount")

    # I1: non-positive amount accepted
    for e in trace:
        if e["method"] == "POST" and e["path"] == "/payments" and _ok(e) and e["body"]:
            if isinstance(e["body"].get("amount"), int) and e["body"]["amount"] <= 0:
                v.append(Violation(invariant="amount_must_be_positive",
                                   detail=f"step {e['step']}: amount {e['body']['amount']} accepted ({e['status']})"))
                break

    # I2: same Idempotency-Key produced different payments
    by_key = defaultdict(set)
    for e in trace:
        key = (e["headers"] or {}).get("Idempotency-Key")
        if key and e["method"] == "POST" and e["path"] == "/payments" and _ok(e) and isinstance(e["json"], dict):
            by_key[key].add(e["json"].get("id"))
    for key, ids in by_key.items():
        if len(ids) > 1:
            v.append(Violation(invariant="idempotency_key_reuse",
                               detail=f"key {key!r} created {len(ids)} payments: {sorted(ids)}"))

    captures, refunds = defaultdict(list), defaultdict(list)
    for e in trace:
        m = PID.match(e["path"])
        if not m:
            continue
        pid, action = m.group(1), m.group(2)
        # I6: unknown id answered with 2xx
        if pid not in created and _ok(e) and not pid.startswith("{"):
            v.append(Violation(invariant="unknown_id_must_404",
                               detail=f"step {e['step']}: {e['method']} {e['path']} returned {e['status']}"))
        if action == "capture" and _ok(e) and pid in created:
            captures[pid].append(e)
        if action == "refund" and _ok(e) and pid in created:
            refunds[pid].append(e)

    # I3: captured more than once
    for pid, es in captures.items():
        if len(es) > 1:
            v.append(Violation(invariant="capture_only_once",
                               detail=f"{pid} captured successfully {len(es)} times"))

    for pid, es in refunds.items():
        # I4: refunds exceed payment amount
        total = sum((e["body"] or {}).get("amount", 0) for e in es)
        amount = created.get(pid)
        if amount is not None and total > amount:
            v.append(Violation(invariant="refunds_within_amount",
                               detail=f"{pid}: {len(es)} refunds total {total} > payment amount {amount}"))
        # I5: refund succeeded without an earlier successful capture
        first_capture = min((c["step"] for c in captures.get(pid, [])), default=None)
        for e in es:
            if first_capture is None or e["step"] <= first_capture:
                v.append(Violation(invariant="refund_requires_capture",
                                   detail=f"{pid}: refund at step {e['step']} succeeded without earlier capture"))
                break
    return v
