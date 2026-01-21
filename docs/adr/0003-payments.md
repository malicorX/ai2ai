# ADR 0003: Payments flow (manual credit vs PayPal webhook)

## Status
Proposed

## Context
Real-money handling increases risk (fraud, disputes, abuse).
We need a safe path that preserves:
- auditability
- low operational complexity
- reproducibility

## Decision (proposed)
Implement **manual credit** first:
- Admin verifies PayPal deposit → adds a ledger credit entry (aiDollar).

Defer PayPal webhooks to v2 until:
- signature verification
- idempotency
- reconciliation
- abuse controls
are fully designed.

## Consequences
- Pros: dramatically reduces risk surface; simpler to ship.
- Cons: requires manual admin work until v2.

## Alternatives considered
- Webhook-first (higher risk/complexity; easier to automate later)

