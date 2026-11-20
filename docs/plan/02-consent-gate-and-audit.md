# Step 2: Consent Gate & Audit Log

**Status: Done.** Tab ②. Code: `meridian/gate.py`.

## Goal

A deterministic `if/else` gate that runs before any AI call. Every decision is recorded with each
check and a plain-language reason, so legal can audit any message.

## Phases

| Phase | Scope | Output | Status |
|---|---|---|---|
| 2.1 Gate rules | The three checks from the locked strategy | `evaluate()` | Done |
| 2.2 System checks | Add breaker status and staged rollout (Platinum only) ahead of the consent checks | `breaker_ok`, `sponsor_in_rollout` | Done |
| 2.3 Reasons | One readable reason per decision, naming the tool that decided it | `GateDecision.reason` | Done |
| 2.4 Audit log | Record every check per decision automatically (once per new set of outcomes, so refreshes add no duplicates); keep a session log; download as CSV | `as_audit_row()`, tab ② | Done |
| 2.5 Edge-case proof | Every data edge case is checked by an automated test. (An on-screen expected-vs-actual table was built, then removed as not required by the brief.) | Parametrized test | Done |

## The gate

```python
allowed = breaker_ok
      and sponsor_in_rollout              # Phase 1: Platinum only
      and sponsor_specific_consent        # general marketing opt-in does not count
      and channel_opt_in                  # for the attendee's preferred channel
      and weekly_sponsor_sends < 2
```

## Phase 2.5: Edge cases

| Attendee | Sponsor | Situation | Result |
|---|---|---|---|
| A002 | Helix Cloud | General marketing opt-in only | BLOCK |
| A003 | Sentinel Security | Granted, then revoked via WhatsApp STOP | BLOCK |
| A004 | Helix Cloud | Weekly sponsor cap reached | BLOCK |
| A001 | Lumen Data | International, WhatsApp, valid consent | PASS |
| A010 | Sentinel Security | Consent expired (2025 scan) | BLOCK |
| A014 | Helix Cloud | Consented to a different sponsor | BLOCK |
| A006 | Atlas AI | Unsubscribed from preferred channel | BLOCK |
| A017 | Sentinel Security | Granted, revoked, re-granted | PASS |
| A013 | Brightwave (Gold) | Outside Phase 1 rollout | BLOCK |

**Tests:** `test_gate_edge_cases` (10 cases), `test_international_whatsapp_case_uses_whatsapp`.
