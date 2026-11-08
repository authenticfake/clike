---
name: journey-payments
description: Use when the product takes payments, refunds or subscriptions through a payment provider, to prove charges happen once, declines and extra authentication are handled visibly, provider webhooks are verified and idempotent, amounts are exact, and the books reconcile.
phases: ["spec", "plan", "kit", "eval", "gate"]
lanes: ["python", "typescript", "node", "java", "dotnet", "go", "rust", "backend"]
domains: ["consumer", "startup", "enterprise"]
runtime_profiles: ["local", "cloud", "local-cloud", "hybrid"]
gate_required: true
scenario_prefix: PAY
scenarios:
  - PAY-01 | required | Charge happens once | If a payment request is retried (double click, network retry, redelivered message), then the system shall charge once, using an idempotency key with the provider, and return the same result.
  - PAY-02 | required | Decline handled | If the provider declines the payment, then the system shall show a readable reason and a next step, and create no paid order.
  - PAY-03 | required | Provider webhook verified and idempotent | If a provider webhook has an invalid signature or repeats an event already processed, then the system shall reject or ignore it without side effects; a valid new event shall update the order once.
  - PAY-04 | required | Exact amounts | When amounts are stored, computed or sent to the provider, the system shall use integer minor units, or a fixed-point decimal with an explicit scale, together with the currency and the stated rounding rule, never binary floating point.
  - PAY-05 | conditional | [Extra customer authentication possible] Pending authentication | When the provider requires extra customer authentication, the system shall keep the order pending, complete it on success and cancel it with a readable message on failure or timeout.
  - PAY-06 | conditional | [Refunds offered] Refunds | When a full or partial refund is issued, the system shall refund at most the captured amount, record it and show the new balance.
  - PAY-07 | conditional | [Orders and payments must match the provider] Reconciliation | If the provider's records and the system's orders disagree, then the system shall flag the mismatch for an operator and never mark an unpaid order as paid.
obligations:
  - Call the provider through an adapter; blocking checks use a fake provider (or the provider's offline test fixtures) and never real money
  - Never store card data; keep the provider's tokens and references only
  - Prove each included scenario with a blocking check recorded in docs/ACCEPTANCE.json
eval_checks:
  - scenario-coverage
gate_implications:
  - block-if-included-scenario-unproven
evidence_required:
  - One blocking check per included scenario, named in ACCEPTANCE.json
---

# Journey: Payments

## Intent

Payment defects cost money directly: a double charge, an order marked paid that was not, a refund
larger than the capture, a rounding error repeated a million times, a forged webhook. Each one is a
tested scenario against a fake provider, so the money paths are proved before any real transaction.

## Use when

Checkout, invoices, subscriptions, wallets, refunds, payouts through a payment provider.

## Do not use when

Prices are shown but no payment is taken.

## How the pipeline uses it

- **SPEC**: list every scenario in `## Scenarios`; state currencies, rounding, the order state machine
  and the source of truth (provider webhook vs synchronous response).
- **PLAN**: the REQ that integrates the provider owns PAY-01..04; refund and reconciliation REQs own
  PAY-06/07.
- **KIT**: tests drive the order state machine with a fake provider and signed fake webhooks; a
  sandbox-provider check is `blocking: false` with `environment_requirements`.

## Valid exclusions

- No extra authentication in the target markets: PAY-05, with that reason. No refunds: PAY-06.
- Not valid: "the provider prevents double charges" without the idempotency key proved.

## Proof per scenario

- PAY-01: submit the same checkout twice; assert one provider charge (fake records keys) and one order.
- PAY-03: post a webhook with a bad signature, then the same valid event twice; assert one state change.
- PAY-04: property test over amounts and quantities; totals equal the sum of line items in minor units.

## Forbidden

- Floating-point money; card numbers in logs, storage or tests.
- Orders marked paid from the client redirect alone, without the provider's confirmation.

## References

- references/test-idioms.md
