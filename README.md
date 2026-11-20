# Meridian Summit · Consent-Gated Sponsor Matchmaker

Phase 1 wedge for the FutureProofing × Meridian Summit engagement: AI sponsor matchmaking for
Platinum sponsors, where a deterministic consent gate runs before any model call.

## Run it

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py          # optional: export ANTHROPIC_API_KEY=... to use Claude
pytest -q                     # 17 tests: gate edge cases, breaker, LLM payload, safety isolation
```

Without `ANTHROPIC_API_KEY` the app uses a transparent rule-based scorer that returns the same
output shape. The gate, ledger, audit log and rollback controls work the same in both modes.

## What the demo shows

| Tab | What it proves |
|---|---|
| ① Reconciliation & Consent Ledger | Six tools with no shared state merge into one attendee view. Consent events from four tools resolve to one ledger: latest event wins, grants expire after 365 days. |
| ② Consent Gate & Audit Log | Plain `if/else` gate: breaker healthy, sponsor in rollout, sponsor-specific consent, channel opt-in, fewer than 2 sponsor sends in 7 days. Every decision records each check and a reason. The audit log downloads as CSV. |
| ③ Sponsor Matchmaking | Only gate-passed attendees reach the matchmaker, with minimized fields (no name, email or company). Any id the model returns that wasn't in the consented set is dropped and flagged. |
| ④ Rollback & Safety | Replay the ops Slack feed: the breaker auto-trips at a 2.60% opt-out/spam rate (threshold 2%). There's also a manual kill switch. In both cases the app falls back to a static pull-only directory. Safety alerts use static human-written templates with enumerated venues and never touch the AI layer. |

## Edge cases in the synthetic data

| Attendee | Sponsor | Situation | Gate |
|---|---|---|---|
| A002 Marcus Webb | Helix Cloud | General marketing opt-in only | BLOCK |
| A003 Sofia Alvarez | Sentinel Security | Granted in app, revoked via WhatsApp `STOP SENTINEL` | BLOCK |
| A004 Daniel Kim | Helix Cloud | 2 sponsor sends in last 7 days (cap) | BLOCK |
| A001 Priya Raman | Lumen Data | India, prefers WhatsApp, valid consent | PASS |
| A010 Kenji Tanaka | Sentinel Security | Consent from a 2025 booth scan (expired) | BLOCK |
| A014 Fatima Al-Sayed | Helix Cloud | Consented to Sentinel, not Helix | BLOCK |
| A006 Lukas Becker | Atlas AI | Valid consent, unsubscribed from email (preferred channel) | BLOCK |
| A017 Nadia Petrova | Sentinel Security | Granted → revoked → re-granted | PASS |
| A013 Grace Liu | Brightwave (Gold) | Non-Platinum sponsor, outside staged rollout | BLOCK |

## Layout

```
app.py                     Streamlit UI only; no business logic
meridian/config.py         every threshold in one place (cap, TTL, trip rate, rollout tiers, model)
meridian/data_loader.py    reads the six tool exports
meridian/ledger.py         reconciliation + master consent ledger
meridian/gate.py           deterministic consent gate + audit rows
meridian/circuit_breaker.py  auto-trip on opt-out/spam rate + manual kill switch
meridian/matchmaker.py     Claude (claude-opus-5-5, structured output) or offline scorer
meridian/safety_alerts.py  static safety templates; imports nothing from the AI layer
data/                      synthetic exports from the six tools
tests/test_wedge.py        brief edge cases and hard-stop guarantees
```
