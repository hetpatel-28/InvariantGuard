import asyncio
from mock_api.app import ALL_BUGS, create_app
from idemtest.checker import check_trace
from idemtest.executor import make_client, run_scenario
from idemtest.models import Scenario, Step
from idemtest.shrink import shrink

S = Step


def run(bugs, scenario):
    async def go():
        async with make_client(create_app(bugs)) as c:
            return check_trace(await run_scenario(c, scenario))
    return asyncio.run(go())


CONCURRENT_REFUND = Scenario(name="race", steps=[
    S(method="POST", path="/payments", body={"amount": 100}, save_as="p"),
    S(method="POST", path="/payments/{p}/capture"),
    S(method="POST", path="/payments/{p}/refund", body={"amount": 70}, repeat=2)])


def test_clean_api_has_no_violations():
    assert run(set(), CONCURRENT_REFUND) == []


def test_race_bug_only_visible_when_concurrent():
    sequential = CONCURRENT_REFUND.model_copy(deep=True)
    sequential.steps[2].repeat = 1
    assert run({"refund_race"}, sequential) == []             # looks fine one request at a time
    assert any(v.invariant == "refunds_within_amount" for v in run({"refund_race"}, CONCURRENT_REFUND))


def test_each_bug_is_a_known_flag():
    for b in ALL_BUGS:
        create_app({b})


def test_shrink_removes_irrelevant_steps():
    noisy = Scenario(name="noisy", steps=[
        S(method="GET", path="/payments/pay_missing"),
        S(method="POST", path="/payments", body={"amount": 100}, save_as="p"),
        S(method="POST", path="/payments/{p}/capture"),
        S(method="POST", path="/payments/{p}/refund", body={"amount": 70}, repeat=5)])
    small = asyncio.run(shrink(lambda: create_app({"refund_race"}), noisy, "refunds_within_amount"))
    assert len(small.steps) == 3 and small.steps[2].repeat == 2
