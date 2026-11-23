# Cost accounting and controls

V1 allows only `gpt-6.2-sol` with the Standard/default service tier. Pricing checked November 22, 2026: input $2 per million tokens and output $10 per million tokens, per the [official model page](https://developers.openai.com/api/docs/models/gpt-6.2-sol.md). Cached inputs are conservatively counted as uncached. These are token-based estimates, not provider invoice verification.

Before each call, an atomic SQLite transaction reserves $0.25. The serialized payload is limited to 80,000 UTF-8 bytes and output to 4,096 tokens, with a margin for token framing at the documented short-context rates. Automatic SDK retries are disabled. Usage settles the reservation after a successful response. A failed, interrupted or unaccounted request retains its full reservation because its actual charge may be unknown. The budget ledger must be retained across invocations.

No more than eight model requests are allowed per investigation. Concurrent processes sharing the same ledger cannot reserve beyond its ceiling. The local ledger cannot control another application, another copy of this repository, a changed ledger path or direct use of the API key. It is not an account-wide hard billing limit. Pricing/model changes require reviewing reservations and the test assumptions before use. Do not reset the ledger to repeat a spending allowance.

The dashboard and CI never initiate paid calls. Adding a public live endpoint, scheduler, auto-recharge, new model or paid hosting requires a separate scope decision. The application does not manage account billing or verify the remaining credit balance.
