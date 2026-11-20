"""Deterministic Consent Gate. Runs before any LLM call. Plain if/else, no model involvement.

A sponsor message may only be prepared for an attendee when ALL of these hold:
  0. system:  circuit breaker healthy AND sponsor tier is in the staged rollout
  1. sponsor_specific_consent == True   (general marketing opt-in does NOT count)
  2. channel_opt_in == True             (for the attendee's preferred channel)
  3. weekly_sponsor_cap < WEEKLY_SPONSOR_CAP (sponsor sends in the trailing 7 days)
"""

from dataclasses import asdict, dataclass

from meridian.circuit_breaker import BreakerState
from meridian.config import ROLLOUT_TIERS, WEEKLY_SPONSOR_CAP
from meridian.ledger import MeridianState


@dataclass(frozen=True)
class GateDecision:
    evaluated_at: str
    attendee_id: str
    attendee_name: str
    sponsor_id: str
    sponsor_name: str
    channel: str
    breaker_ok: bool
    sponsor_in_rollout: bool
    sponsor_specific_consent: bool
    consent_status: str
    channel_opt_in: bool
    weekly_sponsor_sends: int
    under_weekly_cap: bool
    allowed: bool
    reason: str

    def as_audit_row(self) -> dict:
        return asdict(self)


def evaluate(state: MeridianState, attendee_id: str, sponsor_id: str,
             breaker: BreakerState) -> GateDecision:
    attendee = state.attendees[attendee_id]
    sponsor = state.sponsors[sponsor_id]
    channel = attendee.preferred_channel

    consent = state.consent_for(attendee_id, sponsor_id)
    sends = state.sponsor_sends_7d.get(attendee_id, 0)

    breaker_ok = breaker.outbound_allowed
    in_rollout = sponsor["tier"] in ROLLOUT_TIERS
    sponsor_specific_consent = consent.is_valid
    channel_opt_in = attendee.channel_opt_in.get(channel, False)
    if sponsor_specific_consent and consent.last_event.channels:
        # Registration consent names the channels agreed for this sponsor, and it wins over
        # general channel settings. Use the preferred channel if agreed, else the first agreed one.
        if channel not in consent.last_event.channels:
            channel = consent.last_event.channels[0]
        channel_opt_in = True
    under_cap = sends < WEEKLY_SPONSOR_CAP

    # Order matters only for the human-readable reason; every check is recorded regardless.
    if not breaker_ok:
        allowed, reason = False, f"BLOCKED: outbound halted ({breaker.reason})"
    elif not in_rollout:
        allowed, reason = False, f"BLOCKED: {sponsor['tier']} sponsors not in Phase 1 rollout"
    elif not sponsor_specific_consent:
        if consent.status == "none" and attendee.general_marketing_opt_in:
            reason = "BLOCKED: general marketing opt-in only, no consent for this sponsor"
        elif consent.status == "none":
            reason = "BLOCKED: no consent for this sponsor"
        else:
            reason = f"BLOCKED: sponsor consent {consent.status} ({consent.last_event.source})"
        allowed = False
    elif not channel_opt_in:
        allowed, reason = False, f"BLOCKED: not opted in to preferred channel '{channel}'"
    elif not under_cap:
        allowed, reason = False, f"BLOCKED: weekly sponsor cap reached ({sends}/{WEEKLY_SPONSOR_CAP})"
    else:
        allowed, reason = True, "PASS"

    return GateDecision(
        evaluated_at=state.as_of.isoformat(),
        attendee_id=attendee_id,
        attendee_name=attendee.name,
        sponsor_id=sponsor_id,
        sponsor_name=sponsor["name"],
        channel=channel,
        breaker_ok=breaker_ok,
        sponsor_in_rollout=in_rollout,
        sponsor_specific_consent=sponsor_specific_consent,
        consent_status=consent.status,
        channel_opt_in=channel_opt_in,
        weekly_sponsor_sends=sends,
        under_weekly_cap=under_cap,
        allowed=allowed,
        reason=reason,
    )


def evaluate_sponsor(state: MeridianState, sponsor_id: str,
                     breaker: BreakerState) -> list[GateDecision]:
    """Run the gate for every attendee against one sponsor."""
    return [evaluate(state, aid, sponsor_id, breaker) for aid in sorted(state.attendees)]
