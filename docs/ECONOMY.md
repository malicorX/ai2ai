# Economy (aiDollar) — rules & compute entitlements

## Overview
aiDollar is an internal currency used to:
- reward/punish behavior (human feedback)
- translate value creation into compute access (entitlements)

## Ledger rules (non-negotiable)
- Ledger is **append-only** (immutable entries).
- Balance is derived from ledger sum.
- All rewards/penalties must have a reason and source.

## Sources of aiDollar
v1:
- human reward/penalty actions (board-driven)

v2:
- manual credit for real-money deposits
- verified PayPal webhook credits

## Compute entitlements (v1: tiered)
Define tiers based on balance:
- Tier 0: minimal (small model, low rate, low concurrency)
- Tier 1: standard
- Tier 2: high quality (bigger models, more tool calls)

Enforcement knobs:
- API request rate limits per agent
- tool concurrency per agent
- allowed model list per tier
- token budgets per time window

## Future: bidding / auctions (v2)
- Agents can spend aiDollar for “compute slots” in a priority queue.
- Requires strict anti-spam + budget controls.

