# Step 4: Rollback & Safety

**Status: Done.** Tab ④. Code: `meridian/circuit_breaker.py`, `meridian/safety_alerts.py`.

## Goal

If something goes wrong in front of 120,000 people, sponsor outbound must stop automatically.
Safety alerts must never depend on the AI layer.

## Phases

| Phase | Scope | Output | Status |
|---|---|---|---|
| 4.1 Auto circuit breaker | Trip when the latest hourly (opt-outs + spam reports) / sent rate exceeds 2% | `evaluate_breaker()` | Done |
| 4.2 Manual switch | A person can halt all sponsor outbound with one toggle | Sidebar "Circuit breaker" toggle | Done |
| 4.3 Fail closed | When tripped, the gate blocks every sponsor message and matchmaking turns off | Gate system check | Done |
| 4.4 Degraded mode | Fall back to a static, pull-only sponsor directory | Tab ④ | Done |
| 4.5 Replayable incident | Replay the ops Slack feed hour by hour; the spike at 13:00 (2.60%) trips the breaker | Sidebar slider, chart | Done |
| 4.6 Safety alerts | Human-written templates only, enumerated venues and shelter points, not gated, not affected by the circuit breaker | `safety_alerts.py` | Done |
| 4.7 One latching switch | Automatic trip and manual switch are the same toggle: an auto-trip flips it on, and it stays on until a person switches it off, even if complaints fall | `latched_breaker()`, sidebar | Done |
| 4.8 Named manual override | Switching the breaker off needs a person's name; trying to flip the toggle off bounces back. Every trip, manual switch-on and override is logged with time, name, report hour and complaint rate | Sidebar override form, breaker log in tab ④ (CSV) | Done |

## Decisions

| Question | Decision |
|---|---|
| Trip threshold | 2% opt-out/spam rate in the latest hourly window |
| Rollout | Platinum sponsors only in Phase 1 |
| Safety alert wording | Never model-generated (Ines Okafor's hard stop) |
| Who can turn sponsor messages back on? | Only a named person, through Manual override. The breaker latches, like an electrical breaker; a later bad report can trip it again |
| Does stopping messages need a name? | No. Stopping must have no friction; only turning messages back on needs a name |

**Tests:**
- `test_breaker_trips_on_spike_and_blocks_everything`
- `test_manual_kill_switch_blocks_even_when_healthy`
- `test_latched_breaker_stays_tripped_until_switched_off`
- `test_safety_module_is_isolated_from_ai_layer`, which checks that the module imports nothing from the AI layer.
- `test_safety_templates_reject_unknown_venue`
