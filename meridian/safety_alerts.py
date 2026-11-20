"""Safety alerts: 100% human-written static templates. Deliberately outside the AI layer.

This module must never import the matchmaker or any LLM client (enforced by a test).
Templates are approved wording; only enumerated, validated fields may be substituted.
Safety alerts do not pass through the sponsor consent gate or the sponsor circuit breaker.
"""

from datetime import datetime, timezone
from string import Template

VENUES = {
    "MCC-NORTH": "Meridian Convention Center, North Building",
    "MCC-SOUTH": "Meridian Convention Center, South Building",
    "HARBOR-HALL": "Harbor Hall",
    "CIVIC-THEATER": "Civic Theater",
}

SHELTER_POINTS = {
    "MCC-NORTH-B1": "North Building, Level B1 concourse",
    "MCC-SOUTH-B1": "South Building, Level B1 concourse",
    "HARBOR-HALL-LL": "Harbor Hall, Lower Level",
}

TEMPLATES = {
    "severe_weather_shelter": Template(
        "SAFETY ALERT (Meridian Summit): Severe weather warning in effect. "
        "Move now to the shelter point: $shelter_point. Follow staff in orange vests. "
        "Do not leave the building."
    ),
    "room_change": Template(
        "ROOM CHANGE (Meridian Summit): \"$session_title\" has moved to $venue, $room. "
        "Start time is unchanged. Staff at the original room will direct you."
    ),
}


def render(template_id: str, **fields: str) -> str:
    if template_id not in TEMPLATES:
        raise ValueError(f"Unknown safety template: {template_id}")
    if "venue" in fields:
        if fields["venue"] not in VENUES:
            raise ValueError(f"Venue must be one of {sorted(VENUES)}")
        fields["venue"] = VENUES[fields["venue"]]
    if "shelter_point" in fields:
        if fields["shelter_point"] not in SHELTER_POINTS:
            raise ValueError(f"Shelter point must be one of {sorted(SHELTER_POINTS)}")
        fields["shelter_point"] = SHELTER_POINTS[fields["shelter_point"]]
    return TEMPLATES[template_id].substitute(**fields)


MAX_CUSTOM_LENGTH = 480   # keeps a custom alert within a few SMS segments


def make_custom_template(title: str, text: str, author: str, now: datetime | None = None) -> dict:
    """A safety message typed by a named person. Stored as written; never generated or rewritten."""
    title, text, author = title.strip(), text.strip(), author.strip()
    if not author:
        raise ValueError("Enter your name. Every custom safety message records who wrote it.")
    if not title:
        raise ValueError("Give the template a short name.")
    if not text:
        raise ValueError("Type the message.")
    if len(text) > MAX_CUSTOM_LENGTH:
        raise ValueError(f"Keep the message under {MAX_CUSTOM_LENGTH} characters.")
    return {
        "title": title,
        "text": text,
        "added_by": author,
        "added_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "origin": "Human-written",
    }
