# Step 3: Sponsor Matchmaking

**Status: Done.** Tab ③. Code: `meridian/matchmaker.py`, `meridian/credentials.py`.

## Goal

Give Marcus Hale (CRO) a match brief he can demo to Platinum sponsors at the renewal summit,
using only attendees the gate has passed.

## Phases

| Phase | Scope | Output | Status |
|---|---|---|---|
| 3.1 Gate first | Matchmaker accepts only gate-passed decisions; no candidates means no model call | `run_matchmaking()` | Done |
| 3.2 Data minimization | Send role, industry, country, topics and booth visit only. No name, email, phone or company | `minimized_candidate()` | Done |
| 3.3 Claude call | `claude-opus-5-5`, structured output (fit score, rationale, suggested opener), server-side refusal fallback | `_call_claude()` | Done |
| 3.4 Output checks | Drop and flag any attendee id the model returns that wasn't in the consented set | `dropped_ids` | Done |
| 3.5 Offline fallback | Transparent rule-based scorer with the same output shape, used with no key or on any failure | `offline_score()` | Done |
| 3.6 UI | Run gate, then match brief; show the exact payload the model saw and who was blocked | Tab ③ | Done |
| 3.7 Key status | A small box at the bottom of the Control room shows whether an API key is loaded (last 4 characters only) and whether Anthropic accepts it, with a Re-check button | `credentials.py`, sidebar | Done |

## Decisions

| Question | Decision |
|---|---|
| Who writes the final message? | The model suggests an opener; the sponsor approves it before anything is sent |
| What if the model invents an attendee? | It is dropped and flagged, never shown |
| Demo without network or key? | The offline scorer keeps the demo working; the UI says which engine ran |

**Tests:**
- `test_llm_payload_contains_only_gate_passed_and_minimized_data`, which intercepts the real SDK request.
- `test_no_model_call_when_nobody_passes`
- The key masking and verification tests.

## What went wrong and was fixed

The first test imported `httpx`, but the installed Anthropic SDK (2.x) uses `httpx2`. The first
test run failed and the import was corrected.
