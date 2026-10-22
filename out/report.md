# InvariantGuard results

| mode | scenarios | invalid dropped | bugs found | false positives on clean API |
|---|---|---|---|---|
| baseline | 5 | 0 | 2/7 | 0 |
| llm_rag | 12 | 0 | 7/7 | 0 |
| llm_norag | 12 | 0 | 4/7 | 0 |

## Per-bug detection

| bug | baseline | llm_rag | llm_norag |
|---|---|---|---|
| negative_amount | yes | yes | yes |
| idempotency | no | yes | yes |
| double_capture | no | yes | yes |
| refund_overflow | no | yes | no |
| refund_race | no | yes | no |
| refund_before_capture | no | yes | no |
| wrong_status | yes | yes | yes |

## Minimal reproductions (baseline)

- **negative_amount** violates `amount_must_be_positive`: 1 steps shrunk to 1: POST /payments body={'amount': -5}
- **wrong_status** violates `unknown_id_must_404`: 1 steps shrunk to 1: GET /payments/pay_missing

## Minimal reproductions (llm_rag)

- **negative_amount** violates `amount_must_be_positive`: 1 steps shrunk to 1: POST /payments body={'amount': 0, 'currency': 'INR'}
- **idempotency** violates `idempotency_key_reuse`: 2 steps shrunk to 2: POST /payments body={'amount': 100, 'currency': 'INR'}; POST /payments body={'amount': 100, 'currency': 'INR'}
- **double_capture** violates `capture_only_once`: 3 steps shrunk to 3: POST /payments body={'amount': 250, 'currency': 'INR'}; POST /payments/{pid}/capture; POST /payments/{pid}/capture
- **refund_overflow** violates `refunds_within_amount`: 3 steps shrunk to 3: POST /payments body={'amount': 100, 'currency': 'INR'}; POST /payments/{pid}/capture; POST /payments/{pid}/refund body={'amount': 150}
- **refund_race** violates `refunds_within_amount`: 3 steps shrunk to 3: POST /payments body={'amount': 100, 'currency': 'INR'}; POST /payments/{pid}/capture; POST /payments/{pid}/refund x2 concurrently body={'amount': 100}
- **refund_before_capture** violates `refund_requires_capture`: 2 steps shrunk to 2: POST /payments body={'amount': 500, 'currency': 'INR'}; POST /payments/{pid}/refund body={'amount': 500}
- **wrong_status** violates `unknown_id_must_404`: 1 steps shrunk to 1: GET /payments/pay_missing_12345

## Minimal reproductions (llm_norag)

- **negative_amount** violates `amount_must_be_positive`: 2 steps shrunk to 1: POST /payments body={'amount': -500, 'currency': 'INR'}
- **idempotency** violates `idempotency_key_reuse`: 2 steps shrunk to 2: POST /payments body={'amount': 1000, 'currency': 'INR'}; POST /payments body={'amount': 2000, 'currency': 'INR'}
- **double_capture** violates `capture_only_once`: 2 steps shrunk to 2: POST /payments body={'amount': 500, 'currency': 'INR'}; POST /payments/{p_id}/capture x2 concurrently
- **wrong_status** violates `unknown_id_must_404`: 1 steps shrunk to 1: POST /payments/pay_nonexistent/capture
