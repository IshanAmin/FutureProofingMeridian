"""Safety alerts: 100% human-written static templates. Deliberately outside the AI layer.

This module must never import the matchmaker or any LLM client (enforced by a test).
Templates are approved wording; only enumerated, validated fields may be substituted.
Safety alerts do not pass through the sponsor consent gate or the sponsor circuit breaker.
"""

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
