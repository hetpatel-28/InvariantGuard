# Payment API invariants (written by me, in my own words)

- A payment amount must be a positive number; zero and negative amounts must be rejected with a 4xx error.
- Creating a payment twice with the same Idempotency-Key must return the same payment, never a second payment.
- Concurrent create requests that share one Idempotency-Key must still produce only one payment.
- A payment can be captured only once; a second capture must be rejected with 409.
- Concurrent capture requests on the same payment must result in exactly one success.
- The sum of all successful refunds for a payment must never exceed the payment amount.
- Two refunds that are each valid alone but together exceed the payment amount must not both succeed, even when sent at the same time.
- A refund can only be made on a payment that was captured earlier; refunding an authorized payment must be rejected.
- Refund amounts must be positive; zero and negative refunds must be rejected.
- Requesting, capturing or refunding a payment id that does not exist must return 404, not a success status.
- After a payment is fully refunded, any further refund must be rejected.
- Retrying a failed or timed-out request must not change the state in a way that a single success would not.
- The status of a payment must follow the order authorized, captured, partially_refunded or refunded; it must never move backwards.
- Error responses must use 4xx status codes for client mistakes and must not change any payment state.
