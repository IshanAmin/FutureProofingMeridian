"""State reconciliation: merge six tools into one attendee view and one consent ledger.

Consent for an (attendee, sponsor) pair can be granted or revoked in four different
tools. The ledger collects every event, orders them by timestamp, and the latest
event wins. A grant older than CONSENT_TTL_DAYS is treated as expired.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from meridian.config import AS_OF, CAP_WINDOW_DAYS, CONSENT_TTL_DAYS


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class ConsentEvent:
    attendee_id: str
    sponsor_id: str
    action: str          # "grant" | "revoke"
    at: datetime
    source: str          # which of the six tools recorded it
    ref: str             # the source system's own record id


@dataclass(frozen=True)
class ConsentState:
    status: str          # "granted" | "revoked" | "expired" | "none"
    last_event: ConsentEvent | None

    @property
    def is_valid(self) -> bool:
        return self.status == "granted"


NO_CONSENT = ConsentState(status="none", last_event=None)


@dataclass
class Attendee:
    attendee_id: str
    name: str
    email: str
    role: str
    company: str
    industry: str
    country: str
    general_marketing_opt_in: bool
    preferred_channel: str
    channel_opt_in: dict[str, bool]
    topic_interests: list[str]

    @property
    def is_international(self) -> bool:
        return self.country != "US"


@dataclass
class MeridianState:
    as_of: datetime
    attendees: dict[str, Attendee]
    sponsors: dict[str, dict]
    consent_events: list[ConsentEvent]
    consent: dict[tuple[str, str], ConsentState]
    sponsor_sends_7d: Counter
    booth_visits: set[tuple[str, str]] = field(default_factory=set)

    def consent_for(self, attendee_id: str, sponsor_id: str) -> ConsentState:
        return self.consent.get((attendee_id, sponsor_id), NO_CONSENT)


def collect_consent_events(sources: dict[str, dict]) -> list[ConsentEvent]:
    events: list[ConsentEvent] = []

    for scan in sources["badge_scan_vendor"]["booth_scans"]:
        # A booth scan is only consent if the attendee ticked "share my details".
        if scan["share_details_consent"]:
            events.append(ConsentEvent(scan["attendee_id"], scan["sponsor_id"], "grant",
                                       _ts(scan["scanned_at"]), "badge_scan_vendor", scan["scan_id"]))

    for e in sources["mobile_app"]["sponsor_consent_events"]:
        events.append(ConsentEvent(e["attendee_id"], e["sponsor_id"], e["action"],
                                   _ts(e["at"]), "mobile_app", e["event_id"]))

    for e in sources["email_platform"]["preference_center_events"]:
        events.append(ConsentEvent(e["attendee_id"], e["sponsor_id"], e["action"],
                                   _ts(e["at"]), "email_platform", e["event_id"]))

    for e in sources["sms_whatsapp_gateway"]["sponsor_consent_events"]:
        events.append(ConsentEvent(e["attendee_id"], e["sponsor_id"], e["action"],
                                   _ts(e["at"]), "sms_whatsapp_gateway", e["event_id"]))

    return sorted(events, key=lambda ev: ev.at)


def resolve_consent(events: list[ConsentEvent], as_of: datetime,
                    ttl_days: int = CONSENT_TTL_DAYS) -> dict[tuple[str, str], ConsentState]:
    latest: dict[tuple[str, str], ConsentEvent] = {}
    for ev in events:
        if ev.at <= as_of:
            latest[(ev.attendee_id, ev.sponsor_id)] = ev  # events are time-sorted: last write wins

    resolved = {}
    for key, ev in latest.items():
        if ev.action == "revoke":
            status = "revoked"
        elif as_of - ev.at > timedelta(days=ttl_days):
            status = "expired"
        else:
            status = "granted"
        resolved[key] = ConsentState(status=status, last_event=ev)
    return resolved


def count_recent_sponsor_sends(sources: dict[str, dict], as_of: datetime,
                               window_days: int = CAP_WINDOW_DAYS) -> Counter:
    """Sponsor messages per attendee across every channel in the trailing window."""
    window_start = as_of - timedelta(days=window_days)
    sends = (sources["email_platform"]["sponsor_sends"]
             + sources["sms_whatsapp_gateway"]["sponsor_sends"])
    return Counter(s["attendee_id"] for s in sends if window_start < _ts(s["sent_at"]) <= as_of)


def build_attendees(sources: dict[str, dict]) -> dict[str, Attendee]:
    app = {p["attendee_id"]: p for p in sources["mobile_app"]["profiles"]}
    email = {s["attendee_id"]: s for s in sources["email_platform"]["subscribers"]}
    gateway = {c["attendee_id"]: c for c in sources["sms_whatsapp_gateway"]["channel_preferences"]}

    attendees = {}
    for rec in sources["registration_crm"]["attendees"]:
        aid = rec["attendee_id"]
        prefs = gateway.get(aid, {})
        attendees[aid] = Attendee(
            attendee_id=aid,
            name=rec["name"],
            email=rec["email"],
            role=rec["role"],
            company=rec["company"],
            industry=rec["industry"],
            country=rec["country"],
            general_marketing_opt_in=rec["general_marketing_opt_in"],
            preferred_channel=prefs.get("preferred_channel", "email"),
            channel_opt_in={
                "email": not email.get(aid, {}).get("unsubscribed", True),
                "whatsapp": prefs.get("whatsapp_opt_in", False),
                "sms": prefs.get("sms_opt_in", False),
                "push": app.get(aid, {}).get("push_opt_in", False),
            },
            topic_interests=app.get(aid, {}).get("topic_interests", []),
        )
    return attendees


def reconcile(sources: dict[str, dict], as_of: datetime = AS_OF) -> MeridianState:
    events = collect_consent_events(sources)
    badge = sources["badge_scan_vendor"]
    return MeridianState(
        as_of=as_of,
        attendees=build_attendees(sources),
        sponsors={s["sponsor_id"]: s for s in badge["sponsors"]},
        consent_events=events,
        consent=resolve_consent(events, as_of),
        sponsor_sends_7d=count_recent_sponsor_sends(sources, as_of),
        booth_visits={(s["attendee_id"], s["sponsor_id"]) for s in badge["booth_scans"]},
    )


def ledger_rows(state: MeridianState) -> list[dict]:
    """The master Consent Ledger: one row per (attendee, sponsor) pair with any consent history."""
    rows = []
    for (aid, sid), cs in sorted(state.consent.items()):
        attendee, sponsor = state.attendees[aid], state.sponsors[sid]
        rows.append({
            "Attendee": f"{attendee.name} ({aid})",
            "Sponsor": sponsor["name"],
            "Tier": sponsor["tier"],
            "Consent Status": cs.status,
            "Channel": attendee.preferred_channel,
            "Timestamp": cs.last_event.at.strftime("%Y-%m-%d %H:%M UTC"),
            "Decided By": f"{cs.last_event.source} · {cs.last_event.ref}",
        })
    return rows
