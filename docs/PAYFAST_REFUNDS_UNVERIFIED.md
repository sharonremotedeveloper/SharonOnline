# PayFast refunds: what is UNVERIFIED (Task 10.7)

**Status:** `PayFastRefundGateway` is a stub. It returns `manual` for `refund` and `lookup` in every case and makes no HTTP call.
`PAYFAST_REFUNDS_ENABLED` (default false) only lets the router reach the stub; flipping it to true does not move money.
A person refunds PayFast payments from the PayFast dashboard and records it with the Django-admin "mark as paid" action.

**Verification attempt (2026-10-04):** one fetch of `https://developers.payfast.co.za/api` returned only the page header (the docs are a
JavaScript-rendered app), so **nothing below was verified**. Everything is UNVERIFIED until someone reads PayFast's published refund API
(with the sandbox account, `PAYFAST_SANDBOX=True`) and records the answer here.

| Item | Status | What must be confirmed |
| :--- | :--- | :--- |
| Endpoint, method, base URL (live vs sandbox host) | UNVERIFIED | exact path for create refund and for querying a refund; whether `?testing=true` or a separate host selects the sandbox |
| Identifier of the payment to refund | UNVERIFIED | that it is the ITN `pf_payment_id` (our `PaymentTransaction.gateway_reference`) and not the merchant `m_payment_id` |
| Auth headers | UNVERIFIED | required header names (merchant id, API version, timestamp, signature) and the timestamp format/tolerance |
| Signature construction | UNVERIFIED | the API signature differs from the ITN signature: confirm field ordering (alphabetical?), which fields are included (headers + body), encoding, passphrase placement. Do NOT reuse `payfast.build_param_string` |
| Sandbox support | UNVERIFIED | whether refunds can be exercised in the sandbox at all, and with which credentials |
| Idempotency | UNVERIFIED (assumed absent) | if PayFast has no idempotency key, a retried POST can refund twice: the adapter must `lookup` before every retry and treat any ambiguous transport result as "check first" |
| Amounts and currency | UNVERIFIED | unit (rands vs cents), decimal format, partial vs full refunds, ZAR only, cumulative limits |
| Refund states / polling | UNVERIFIED | the status values, whether a refund is instant or pending, how to read it back |
| Error codes | UNVERIFIED | which HTTP statuses/codes mean "permanent refusal" (map to `rejected`) vs "retry" (`transient`), rate limits, `Retry-After` |
| Refund window and balance rules | UNVERIFIED | time limit, and whether the merchant balance must cover the refund |
| Webhook / ITN for refunds | UNVERIFIED | whether PayFast notifies us of a refund, and what the ITN looks like |

Before enabling: implement the adapter against the verified docs with mocked HTTP tests, a lookup-before-retry rule, and the same
no-secrets logging rules as PayPal (never log the passphrase, signature or parameter string); then run one sandbox refund by hand.
