# InvariantGuard: AI-Assisted Stateful & Concurrent API Testing for Payment Systems

An LLM proposes multi-step and concurrent test scenarios for a REST payment API, using business
rules (invariants) retrieved with RAG. Plain Python executes the scenarios and a deterministic
checker decides pass/fail, so the model never judges its own output. Failing scenarios are shrunk
to minimal reproductions.

> Independent learning project on a mock API. Commercial payment-testing tools exist; this explores
> whether RAG-grounded LLM scenarios can find stateful and concurrency logic bugs. Not affiliated
> with any company.

## How it works

OpenAPI spec -> RAG over invariants.md -> LLM -> Pydantic-validated scenarios
-> async executor (httpx, concurrent steps) -> deterministic checker -> shrinker -> report

- `mock_api/app.py`: FastAPI payment API with 7 switchable bugs (negative amount, idempotency,
  double capture, refund overflow, refund race, refund before capture, wrong status code).
- `idemtest/`: generator, executor, checker (6 invariants), shrinker, evaluation runner.
- `knowledge/invariants.md`: the business rules used for retrieval.

## Run it

    pip install -r requirements.txt
    python -m pytest -q
    python -m idemtest.run_eval --provider mock          # offline wiring check, not a real result
    # real run (set your own key first; never commit it):
    #   PowerShell: $env:GEMINI_API_KEY="..."; $env:LLM_MODEL="gemini-3.5-flash-lite"
    python -m idemtest.run_eval --provider gemini --regen

## Results

Three independent runs (Gemini `gemini-3.5-flash-lite`, temperature 0.8) against the mock API with
7 planted bugs. Retrieval method: word-overlap (`bow`).

| Run | baseline (no LLM) | LLM + RAG | LLM without RAG |
|---|---|---|---|
| 1 | 2/7 | 7/7 | 4/7 |
| 2 | 2/7 | 6/7 | 7/7 |
| 3 | 2/7 | 7/7 | 4/7 |
| Mean | 2.0 | 6.7 | 5.0 |

No false positives on the clean API in any run. Full reports are in `out/`.

With 3 runs and 7 bugs, the RAG advantage is suggestive, not statistically established
(run 2 went the other way).

## Limitations

- The bugs and the invariants were written by the same person, so retrieval had an easy match.
- The RAG and no-RAG prompts differ in more than the retrieved rules (the RAG prompt also tells the
  model to try to violate the rules).
- Small sample: 3 runs, 7 bugs. LLM output varies run to run.
- The checker covers 6 invariants; anything outside them is not detected.
- Evaluated only on a mock API, not on real systems.