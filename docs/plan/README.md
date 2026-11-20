# Phase 1 Wedge: Build Plan by Step and Phase

**Wedge:** consent-gated sponsor matchmaking for Platinum sponsors first.
**Rule that shapes everything:** no sponsor message, and no AI call about an attendee, without valid
sponsor-specific consent.

The prototype is split into six **steps**, one per tab in the app. Each step is split into
**phases** that could each be built, tested and reviewed on their own.

| Step | Tab | What it does | Status |
|---|---|---|---|
| [0. Registration & Consent](00-registration-and-consent.md) | ⓪ Customer View | The attendee's registration and consent screens, in a browser outline | Done |
| [1. Reconciliation & Consent Ledger](01-reconciliation-and-ledger.md) | ① | Merge six disconnected tools into one consent ledger | Done |
| [2. Consent Gate & Audit Log](02-consent-gate-and-audit.md) | ② | Deterministic pass/block before any AI call | Done |
| [3. Sponsor Matchmaking](03-sponsor-matchmaking.md) | ③ | Rank consented attendees for a Platinum sponsor | Done |
| [4. Rollback & Safety](04-rollback-and-safety.md) | ④ | Latching circuit breaker, static safety alerts | Done |
| [5. ROI Simulator](05-roi-simulator.md) | ⑤ | Payback on the $650K Phase 1 fee | Done |

## How the steps connect

```
Step 0  Attendee registers and says yes/no per sponsor, per channel ──┐
Step 1  Six tools' consent records ─────────────────────────────────┴─► one Consent Ledger
Step 2  Ledger ──► deterministic gate ──► audit log
Step 3  Only gate-passed attendees ──► matchmaker (Claude or offline scorer)
Step 4  Opt-out spike or manual switch ──► circuit breaker ──► gate blocks everything ──► static directory
Step 5  Retained Platinum revenue + support savings ──► payback vs $650K
```

## Build order (honest record)

Steps 1–5 were built in that order and are documented here phase by phase, with the decisions
behind each phase recorded inline. Step 0 was added afterwards and planned in phases before any
code was written.

## Conventions

- **Status:** Done · Active · Next · Not started · Out of scope (prototype).
- **Proof:** every Done phase names the file it lives in and the tests that check it
  (`tests/test_wedge.py`, run with `pytest -q`).
