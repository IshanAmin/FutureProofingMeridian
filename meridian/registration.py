"""Step 0: turn an attendee's registration form into records the ledger and gate already understand.

Pure functions only. The customer view keeps registrations in the viewer's session, so nothing
personal is written to disk and reviewers on a shared link never see each other's entries.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from meridian.ledger import Attendee, ConsentEvent

# Draft wording. Needs General Counsel sign-off before real use.
CONSENT_VERSION = "2026-11-v1"
CHANNELS = {"email": "Email", "whatsapp": "WhatsApp", "sms": "Text message (SMS)"}
SOURCE = "registration_form"


def describe_channels(channels) -> str:
    return ", ".join(CHANNELS.get(c, c) for c in channels) or "none"


def consent_wording(sponsor_name: str, channels) -> str:
    return (f"Yes, {sponsor_name} may contact me about its products and meetings by "
            f"{describe_channels(channels)}. Meridian sends these messages for them. "
            "I can stop at any time.")


@dataclass(frozen=True)
class RegistrationForm:
    name: str
    email: str
    phone: str
    company: str
    role: str
    industry: str
    country: str
    preferred_channel: str
    event_news_opt_in: bool
    topic_interests: tuple[str, ...]
    sponsor_channels: dict[str, tuple[str, ...]]   # sponsor_id -> channels ticked (empty = no)


@dataclass(frozen=True)
class Registration:
    attendee: Attendee
    consent_events: tuple[ConsentEvent, ...]
    registered_at: datetime


def validate(form: RegistrationForm) -> list[str]:
    errors = []
    if not form.name.strip():
        errors.append("Enter your name.")
    if "@" not in form.email or "." not in form.email.split("@")[-1]:
        errors.append("Enter a valid work email.")
    if not form.company.strip() or not form.role.strip():
        errors.append("Enter your company and job title.")
    uses_phone = form.preferred_channel in ("whatsapp", "sms") or any(
        ch in ("whatsapp", "sms") for chs in form.sponsor_channels.values() for ch in chs)
    if uses_phone and not form.phone.strip():
        errors.append("Add a mobile number to use WhatsApp or text messages.")
    return errors


def register(form: RegistrationForm, attendee_id: str, at: datetime | None = None) -> Registration:
    """One attendee record, plus one consent grant per sponsor with at least one channel ticked."""
    errors = validate(form)
    if errors:
        raise ValueError(" ".join(errors))
    at = at or datetime.now(timezone.utc)

    attendee = Attendee(
        attendee_id=attendee_id,
        name=form.name.strip(),
        email=form.email.strip(),
        role=form.role.strip(),
        company=form.company.strip(),
        industry=form.industry,
        country=form.country,
        general_marketing_opt_in=form.event_news_opt_in,   # Meridian news only, never sponsor consent
        preferred_channel=form.preferred_channel,
        channel_opt_in={c: False for c in (*CHANNELS, "push")},  # sponsor consent decides channels
        topic_interests=list(form.topic_interests),
    )
    events = tuple(
        ConsentEvent(
            attendee_id=attendee_id, sponsor_id=sponsor_id, action="grant", at=at, source=SOURCE,
            ref=f"REG-{attendee_id}-{sponsor_id}-v{CONSENT_VERSION}",
            channels=tuple(c for c in CHANNELS if c in channels),
        )
        for sponsor_id, channels in form.sponsor_channels.items()
        if any(c in CHANNELS for c in channels)
    )
    return Registration(attendee=attendee, consent_events=events, registered_at=at)


def next_attendee_id(existing_ids) -> str:
    n = 1
    while f"R{n:03d}" in existing_ids:
        n += 1
    return f"R{n:03d}"
