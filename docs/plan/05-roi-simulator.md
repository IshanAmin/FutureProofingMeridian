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

## Default numbers (from the locked strategy)

| Scenario | Benefit | Result |
|---|---|---|
| 30% support cut + 3 Platinum retained | $876K | +$226K, pays back at week 5 |
| 30% support cut + 1.5pp renewal lift | $846K | Pays back at week 5 |
| 30% support cut + 1 Platinum retained | $376K | −$274K, does not pay back |
| Support cut only | $126K | Covers 19% of the fee |

## Open input

The messaging and inference pass-through cost defaults to $0 because there is no real figure yet.
Enter an estimate before presenting.

**Tests:** `test_roi_matches_locked_strategy_numbers`.
