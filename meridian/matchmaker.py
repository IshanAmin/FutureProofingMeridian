"""AI sponsor matchmaking. Only ever sees attendees the Consent Gate has already passed.

Data minimization: the model receives role, industry, country, topic interests and whether
the attendee visited this sponsor's booth last year. Never name, email, phone or company.

If no API credentials are available, or the call fails or is refused, a transparent
rule-based scorer produces the same output shape so the demo never depends on the network.
"""

import json
from dataclasses import dataclass

from pydantic import BaseModel, Field

from meridian.config import FALLBACK_BETA, MODEL
from meridian.gate import GateDecision
from meridian.ledger import MeridianState

SYSTEM_PROMPT = """You are the sponsor matchmaking engine for Meridian Summit, a large technology conference.
You rank attendees for one Platinum sponsor so its sales team can request meetings.

Every attendee you are given has already given verifiable consent to hear from this specific
sponsor on their preferred channel. You do not decide consent; never mention consent in output.

For each attendee, return:
- fit_score: 0-100, how well the attendee matches the sponsor's target buyer profile
  (role seniority and buying authority first, then topic overlap, then industry).
- rationale: one sentence a sponsor sales rep can read in five seconds. Cite the specific
  role/topic/industry overlap. No speculation about budget or intent beyond the data given.
- suggested_opener: one or two sentences the sponsor could send to request a 20-minute meeting
  at their booth. Professional, specific to the attendee's interests, no hype, no emojis,
  under 280 characters. Do not invent facts about the sponsor's products.

Return exactly one entry per attendee_id you were given, using those ids verbatim."""


class Match(BaseModel):
    attendee_id: str
    fit_score: int = Field(ge=0, le=100)
    rationale: str
    suggested_opener: str


class MatchBrief(BaseModel):
    matches: list[Match]


@dataclass
class MatchRun:
    sponsor_id: str
    mode: str                      # "llm" | "offline"
    matches: list[Match]
    payload: list[dict]            # exact minimized data the model sees (or offline scorer uses)
    note: str = ""
    dropped_ids: list[str] | None = None


def minimized_candidate(state: MeridianState, decision: GateDecision) -> dict:
    a = state.attendees[decision.attendee_id]
    return {
        "attendee_id": a.attendee_id,
        "role": a.role,
        "industry": a.industry,
        "country": a.country,
        "topic_interests": a.topic_interests,
        "visited_booth_last_year": (a.attendee_id, decision.sponsor_id) in state.booth_visits,
    }


def sponsor_brief(sponsor: dict) -> dict:
    return {"name": sponsor["name"], "target_buyer_profile": sponsor["target_buyer_profile"]}


def offline_score(sponsor: dict, candidate: dict) -> Match:
    profile = sponsor["target_buyer_profile"]
    role_hit = candidate["role"] in profile["roles"]
    topics = sorted(set(candidate["topic_interests"]) & set(profile["topics"]))
    industry_hit = not profile["industries"] or candidate["industry"] in profile["industries"]

    score = (50 if role_hit else 15) + min(len(topics), 2) * 15 + (10 if industry_hit else 0)
    score += 10 if candidate["visited_booth_last_year"] else 0
    score = min(score, 100)

    parts = [f"{candidate['role']} ({'target role' if role_hit else 'adjacent role'})"]
    if topics:
        parts.append(f"interested in {', '.join(topics)}")
    if candidate["visited_booth_last_year"]:
        parts.append("visited your booth last year")
    topic_line = topics[0] if topics else "your team's priorities"
    return Match(
        attendee_id=candidate["attendee_id"],
        fit_score=score,
        rationale="; ".join(parts) + ".",
        suggested_opener=(f"Hi, the {sponsor['name']} team would value 20 minutes at our booth "
                          f"to compare notes on {topic_line}. Would a slot on Day 1 or 2 work?"),
    )


def _call_claude(sponsor: dict, candidates: list[dict], client) -> MatchBrief:
    user_msg = (
        "Sponsor:\n" + json.dumps(sponsor_brief(sponsor), indent=2)
        + "\n\nConsented attendees:\n" + json.dumps(candidates, indent=2)
    )
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        output_format=MatchBrief,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Model declined the request")
    if response.parsed_output is None:
        raise RuntimeError(f"No structured output (stop_reason={response.stop_reason})")
    return response.parsed_output


def run_matchmaking(state: MeridianState, sponsor_id: str, decisions: list[GateDecision],
                    use_llm: bool = True, client=None) -> MatchRun:
    # Defense in depth: refuse to build a payload containing anyone the gate did not pass.
    passed = [d for d in decisions if d.allowed]
    if any(d.sponsor_id != sponsor_id for d in passed):
        raise ValueError("Gate decisions belong to a different sponsor")

    sponsor = state.sponsors[sponsor_id]
    candidates = [minimized_candidate(state, d) for d in passed]
    if not candidates:
        return MatchRun(sponsor_id, "none", [], [], note="No attendees passed the gate; no model call made.")

    note = ""
    if use_llm:
        try:
            if client is None:
                import anthropic
                client = anthropic.Anthropic()
            brief = _call_claude(sponsor, candidates, client)
            allowed_ids = {c["attendee_id"] for c in candidates}
            kept = [m for m in brief.matches if m.attendee_id in allowed_ids]
            dropped = [m.attendee_id for m in brief.matches if m.attendee_id not in allowed_ids]
            return MatchRun(sponsor_id, "llm", sorted(kept, key=lambda m: -m.fit_score),
                            candidates, dropped_ids=dropped or None)
        except Exception as exc:  # any auth/network/refusal failure degrades to offline scoring
            note = f"LLM unavailable ({type(exc).__name__}: {exc}); used offline scorer."

    matches = sorted((offline_score(sponsor, c) for c in candidates), key=lambda m: -m.fit_score)
    return MatchRun(sponsor_id, "offline", matches, candidates, note=note)
