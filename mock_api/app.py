"""Mock payment API with switchable bugs.

create_app(bugs=set()) -> a CORRECT API.
create_app({"refund_race"}) -> same API with that bug turned on.
"""
import asyncio
import itertools
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

ALL_BUGS = [
    "negative_amount",       # accepts amount <= 0
    "idempotency",           # same Idempotency-Key creates a second payment
    "double_capture",        # a payment can be captured twice
    "refund_overflow",       # total refunds can exceed the payment amount
    "refund_race",           # overflow only under concurrent refunds (check-then-act race)
    "refund_before_capture", # refund allowed on a payment that was never captured
    "wrong_status",          # unknown id returns 200 instead of 404
]


class PaymentIn(BaseModel):
    amount: int
    currency: str = "INR"


class RefundIn(BaseModel):
    amount: int


def create_app(bugs: Optional[set] = None) -> FastAPI:
    bugs = set(bugs or [])
    unknown = bugs - set(ALL_BUGS)
    if unknown:
        raise ValueError(f"unknown bugs: {unknown}")

    app = FastAPI(title="Mock Payments API", version="1.0")
    payments: dict = {}
    idem_keys: dict = {}
    counter = itertools.count(1)

    def get_or_404(pid: str):
        p = payments.get(pid)
        if p is None:
            if "wrong_status" in bugs:
                return None  # caller returns a 200 with an error body (the bug)
            raise HTTPException(status_code=404, detail="payment not found")
        return p

    @app.post("/payments", status_code=201, summary="Create (authorize) a payment")
    async def create_payment(body: PaymentIn, idempotency_key: Optional[str] = Header(default=None)):
        if body.amount <= 0 and "negative_amount" not in bugs:
            raise HTTPException(status_code=400, detail="amount must be positive")
        if idempotency_key and "idempotency" not in bugs and idempotency_key in idem_keys:
            return payments[idem_keys[idempotency_key]]
        pid = f"pay_{next(counter)}"
        payments[pid] = {"id": pid, "amount": body.amount, "currency": body.currency,
                         "status": "authorized", "captured": 0, "refunded": 0}
        if idempotency_key:
            idem_keys[idempotency_key] = pid
        return payments[pid]

    @app.get("/payments/{pid}", summary="Get a payment")
    async def get_payment(pid: str):
        p = get_or_404(pid)
        return p if p is not None else {"error": "not found"}

    @app.post("/payments/{pid}/capture", summary="Capture an authorized payment")
    async def capture(pid: str):
        p = get_or_404(pid)
        if p is None:
            return {"error": "not found"}
        if p["status"] != "authorized" and "double_capture" not in bugs:
            raise HTTPException(status_code=409, detail="payment already captured")
        p["status"] = "captured"
        p["captured"] = p["amount"]
        return p

    @app.post("/payments/{pid}/refund", summary="Refund a captured payment")
    async def refund(pid: str, body: RefundIn):
        p = get_or_404(pid)
        if p is None:
            return {"error": "not found"}
        if body.amount <= 0:
            raise HTTPException(status_code=400, detail="refund must be positive")
        if p["status"] not in ("captured", "partially_refunded", "refunded") \
                and "refund_before_capture" not in bugs:
            raise HTTPException(status_code=409, detail="payment not captured")
        if "refund_overflow" not in bugs and p["refunded"] + body.amount > p["amount"]:
            raise HTTPException(status_code=409, detail="refund exceeds payment amount")
        if "refund_race" in bugs:
            await asyncio.sleep(0.01)  # gap between check and update -> race window
            # the check above used a stale value of p["refunded"]
        p["refunded"] += body.amount
        p["status"] = "refunded" if p["refunded"] >= p["amount"] else "partially_refunded"
        return p

    return app


app = create_app()  # `uvicorn mock_api.app:app` runs the correct API
