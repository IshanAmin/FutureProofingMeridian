"""Phase 1 payback model for Meridian's CFO. Pure functions; the UI only supplies inputs.

Benefits land on the engagement timeline, not evenly:
  week 5  - 2027 sponsor contracts lock  -> retained sponsor revenue is booked
  week 14 - event week                   -> support payroll savings are realized
"""

import math
from dataclasses import dataclass

CONTRACT_LOCK_WEEK = 5
EVENT_WEEK = 14


@dataclass(frozen=True)
class RoiInputs:
    phase1_fee: float = 650_000
    support_payroll: float = 420_000
    support_reduction_pct: float = 30.0
    sponsor_revenue: float = 48_000_000
    yoy_renewal_drop_pct: float = 14.0
    retention_mode: str = "platinum"          # "platinum" | "portfolio"
    platinum_fee: float = 250_000
    platinum_retained: int = 3
    renewal_lift_pct: float = 1.5             # percentage points on the whole sponsor book
    pass_through_costs: float = 0.0           # messaging + AI costs, paid by Meridian on top of the fee


@dataclass(frozen=True)
class RoiResult:
    support_savings: float
    retained_revenue: float
    total_benefit: float
    net_benefit: float
    roi_pct: float
    payback_multiple: float
    churn_dollars: float
    churn_recovered_pct: float
    support_only_coverage_pct: float
    platinum_needed_to_break_even: int
    payback_week: int | None


def compute(i: RoiInputs) -> RoiResult:
    support_savings = i.support_payroll * i.support_reduction_pct / 100
    if i.retention_mode == "platinum":
        retained = i.platinum_retained * i.platinum_fee
    else:
        retained = i.sponsor_revenue * i.renewal_lift_pct / 100

    total_cost = i.phase1_fee + i.pass_through_costs
    total_benefit = support_savings + retained
    churn = i.sponsor_revenue * i.yoy_renewal_drop_pct / 100

    shortfall = max(total_cost - support_savings, 0)
    platinum_needed = math.ceil(shortfall / i.platinum_fee) if i.platinum_fee else 0

    if retained >= total_cost:
        payback_week = CONTRACT_LOCK_WEEK
    elif total_benefit >= total_cost:
        payback_week = EVENT_WEEK
    else:
        payback_week = None

    return RoiResult(
        support_savings=support_savings,
        retained_revenue=retained,
        total_benefit=total_benefit,
        net_benefit=total_benefit - total_cost,
        roi_pct=(total_benefit - total_cost) / total_cost * 100 if total_cost else 0.0,
        payback_multiple=total_benefit / total_cost if total_cost else 0.0,
        churn_dollars=churn,
        churn_recovered_pct=retained / churn * 100 if churn else 0.0,
        support_only_coverage_pct=support_savings / total_cost * 100 if total_cost else 0.0,
        platinum_needed_to_break_even=platinum_needed,
        payback_week=payback_week,
    )


def cumulative_timeline(i: RoiInputs, r: RoiResult, weeks: int = 16) -> list[dict]:
    """Week-by-week cumulative cost vs benefit for the payback chart."""
    rows = []
    for week in range(weeks + 1):
        benefit = (r.retained_revenue if week >= CONTRACT_LOCK_WEEK else 0) \
                  + (r.support_savings if week >= EVENT_WEEK else 0)
        rows.append({"Week": week, "Cumulative benefit": benefit,
                     "Phase 1 cost": i.phase1_fee + i.pass_through_costs})
    return rows


# ---------------------------------------------------------------- messaging + AI cost estimate
# Rough planning assumptions for Phase 1 (Platinum only, through event week). Every number is an
# assumption to be replaced with Meridian's real volumes and vendor rates.
PASS_THROUGH_ASSUMPTIONS = {
    "in_person_attendees": 120_000,
    "share_consenting_to_a_platinum_sponsor": 0.20,
    "sponsor_messages_per_consenting_attendee": 6,     # weekly cap is 2; most weeks send fewer
    "channel_mix": {"whatsapp": 0.40, "sms": 0.20, "email": 0.40},
    "cost_per_message_usd": {"whatsapp": 0.05, "sms": 0.02, "email": 0.001},
    "platinum_sponsors": 40,
    "match_runs_per_sponsor": 14,                      # one refresh a week until the event
    "ai_cost_per_match_run_usd": 6.00,                 # ~240K input + ~240K output tokens on claude-opus-5-5
    "contingency_multiplier": 2.0,                     # retries, re-runs, rate variance by country
}


def estimate_pass_through(a: dict = PASS_THROUGH_ASSUMPTIONS) -> dict:
    messages = (a["in_person_attendees"] * a["share_consenting_to_a_platinum_sponsor"]
                * a["sponsor_messages_per_consenting_attendee"])
    per_message = sum(a["channel_mix"][ch] * a["cost_per_message_usd"][ch] for ch in a["channel_mix"])
    messaging = messages * per_message
    ai = a["platinum_sponsors"] * a["match_runs_per_sponsor"] * a["ai_cost_per_match_run_usd"]
    subtotal = messaging + ai
    total = subtotal * a["contingency_multiplier"]
    return {
        "messages": messages,
        "messaging_usd": messaging,
        "ai_usd": ai,
        "subtotal_usd": subtotal,
        "total_usd": total,
        "rounded_usd": math.ceil(total / 5_000) * 5_000,
    }
