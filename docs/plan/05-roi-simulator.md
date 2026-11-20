# Step 5: ROI Simulator

**Status: Done.** Tab ⑤. Code: `meridian/roi.py`.

## Goal

Answer Tom Brandt (CFO): "Show me the payback on the $650K." Show why support savings alone
don't get there and sponsor retention does.

## Phases

| Phase | Scope | Output | Status |
|---|---|---|---|
| 5.1 Model | Pure functions for benefit, net, ROI, payback multiple, churn recovered, break-even sponsors | `compute()` | Done |
| 5.2 Timeline | Benefits land when they really do: retained revenue at contract lock (week 5), support savings at event week (week 14) | `cumulative_timeline()` | Done |
| 5.3 Two retention framings | Count of Platinum sponsors retained, or a renewal-rate lift on the $48M book (not both, to avoid double counting) | Radio toggle | Done |
| 5.4 UI | Editable inputs, headline metrics, payback chart, three plain-language takeaways | Tab ⑤ | Done |
| 5.5 Messaging + AI cost estimate | Default messaging + AI cost from stated assumptions, with the arithmetic shown in the tab | `estimate_pass_through()` | Done |

## Default numbers (locked strategy, with the $15K messaging + AI cost estimate)

| Scenario | Benefit | Result |
|---|---|---|
| 30% support cut + 3 Platinum retained | $876K | +$211K, pays back at week 5 |
| 30% support cut + 1.5pp renewal lift | $846K | +$181K, pays back at week 5 |
| 30% support cut + 1 Platinum retained | $376K | −$289K, does not pay back |
| Support cut only | $126K | Covers 19% of the fee and costs |

## Phase 5.5: Messaging + AI cost estimate

Messaging and AI costs are paid by Meridian on top of the fee. The default is a planning estimate
built from stated assumptions (`PASS_THROUGH_ASSUMPTIONS` in `roi.py`), shown line by line in the tab:

- **Messaging, about $3.5K:** 120,000 attendees × 20% saying yes to a Platinum sponsor × 6 messages each
  = 144,000 messages. WhatsApp 40% at $0.05, SMS 20% at $0.02, email 40% at $0.001.
- **AI matchmaking, about $3.4K:** 40 Platinum sponsors × 14 weekly runs × $6 per run on claude-opus-5-5.
- **Total:** subtotal $6.9K × 2 for contingency = $13.7K, rounded up to **$15K**.

These are assumptions, not quotes; WhatsApp and SMS prices vary by country.

**Tests:** `test_roi_matches_locked_strategy_numbers`, `test_pass_through_estimate_keeps_week_5_payback`.
