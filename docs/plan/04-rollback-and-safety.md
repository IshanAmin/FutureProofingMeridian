# Step 4: Rollback & Safety

**Status: Done.** Tab ④. Code: `meridian/circuit_breaker.py`, `meridian/safety_alerts.py`.

## Goal

If something goes wrong in front of 120,000 people, sponsor outbound must stop automatically.
Safety alerts must never depend on the AI layer.

## Phases

| Phase | Scope | Output | Status |
|---|---|---|---|
| 4.1 Auto circuit breaker | Trip when the latest hourly (opt-outs + spam reports) / sent rate exceeds 2% | `evaluate_breaker()` | Done |
| 4.2 Manual kill switch | One toggle halts all sponsor outbound | Sidebar toggle | Done |
| 4.3 Fail closed | When tripped, the gate blocks every sponsor message and matchmaking turns off | Gate system check | Done |
| 4.4 Degraded mode | Fall back to a static, pull-only sponsor directory | Tab ④ | Done |
| 4.5 Replayable incident | Replay the ops Slack feed hour by hour; the spike at 13:00 (2.60%) trips the breaker | Sidebar slider, chart | Done |
| 4.6 Safety alerts | Human-written templates only, enumerated venues and shelter points, not gated, not affected by the kill switch | `safety_alerts.py` | Done |

## Decisions

| Question | Decision |
|---|---|
| Trip threshold | 2% opt-out/spam rate in the latest hourly window |
| Rollout | Platinum sponsors only in Phase 1 |
| Safety alert wording | Never model-generated (Ines Okafor's hard stop) |

**Tests:**
- `test_breaker_trips_on_spike_and_blocks_everything`
- `test_manual_kill_switch_blocks_even_when_healthy`
- `test_safety_module_is_isolated_from_ai_layer`, which checks that the module imports nothing from the AI layer.
- `test_safety_templates_reject_unknown_venue`
