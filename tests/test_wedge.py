import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx2 as httpx  # anthropic>=2 ships on httpx2
import pytest

from meridian import safety_alerts
from meridian.circuit_breaker import evaluate_breaker
from meridian.config import AS_OF
from meridian.credentials import detect_key, verify_key
from meridian.data_loader import load_sources
from meridian.gate import evaluate, evaluate_sponsor
from meridian.ledger import reconcile
from meridian.matchmaker import run_matchmaking

SOURCES = load_sources()
STATE = reconcile(SOURCES, AS_OF)
SLACK = SOURCES["ops_slack"]["messages"]
HEALTHY = evaluate_breaker(SLACK, datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc))


@pytest.mark.parametrize("attendee, sponsor, allowed, reason_fragment", [
    ("A002", "SP01", False, "general marketing opt-in only"),   # brief: general opt-in, no sponsor consent
    ("A003", "SP02", False, "revoked"),                          # brief: granted then revoked
    ("A004", "SP01", False, "weekly sponsor cap"),               # brief: frequency cap
    ("A001", "SP03", True, "PASS"),                              # brief: international WhatsApp, valid consent
    ("A010", "SP02", False, "expired"),
    ("A014", "SP01", False, "no consent for this sponsor"),
    ("A006", "SP05", False, "preferred channel"),
    ("A017", "SP02", True, "PASS"),
    ("A013", "SG01", False, "not in Phase 1 rollout"),
    ("A018", "SP01", True, "PASS"),                              # 1 send in window, under cap
])
def test_gate_edge_cases(attendee, sponsor, allowed, reason_fragment):
    d = evaluate(STATE, attendee, sponsor, HEALTHY)
    assert d.allowed is allowed
    assert reason_fragment in d.reason


def test_international_whatsapp_case_uses_whatsapp():
    d = evaluate(STATE, "A001", "SP03", HEALTHY)
    assert STATE.attendees["A001"].is_international and d.channel == "whatsapp"


def test_breaker_trips_on_spike_and_blocks_everything():
    tripped = evaluate_breaker(SLACK, datetime(2026, 11, 20, 13, 0, tzinfo=timezone.utc))
    assert tripped.tripped and tripped.latest_rate > 0.02
    assert not any(d.allowed for sid in STATE.sponsors for d in evaluate_sponsor(STATE, sid, tripped))


def test_manual_kill_switch_blocks_even_when_healthy():
    killed = evaluate_breaker(SLACK, datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc), kill_switch=True)
    assert killed.manual_kill and not evaluate(STATE, "A001", "SP03", killed).allowed


def _fake_client(captured: list) -> anthropic.Anthropic:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append(body)
        ids = [c["attendee_id"] for c in json.loads(body["messages"][0]["content"].split("Consented attendees:\n", 1)[1])]
        brief = {"matches": [{"attendee_id": i, "fit_score": 80, "rationale": "r", "suggested_opener": "o"} for i in ids]
                 + [{"attendee_id": "A999", "fit_score": 99, "rationale": "invented", "suggested_opener": "x"}]}
        return httpx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps(brief)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })
    return anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_llm_payload_contains_only_gate_passed_and_minimized_data():
    captured: list = []
    decisions = evaluate_sponsor(STATE, "SP01", HEALTHY)
    run = run_matchmaking(STATE, "SP01", decisions, use_llm=True, client=_fake_client(captured))

    assert run.mode == "llm" and len(captured) == 1
    sent = captured[0]["messages"][0]["content"]
    passed = {d.attendee_id for d in decisions if d.allowed}
    blocked = {d.attendee_id for d in decisions if not d.allowed}
    assert all(aid in sent for aid in passed)
    assert not any(f'"{aid}"' in sent for aid in blocked)
    for a in STATE.attendees.values():                     # no PII reaches the model
        assert a.name not in sent and a.email not in sent and a.company not in sent
    assert {m.attendee_id for m in run.matches} == passed  # hallucinated A999 is dropped
    assert run.dropped_ids == ["A999"]


def test_no_model_call_when_nobody_passes():
    captured: list = []
    decisions = evaluate_sponsor(STATE, "SG01", HEALTHY)
    run = run_matchmaking(STATE, "SG01", decisions, use_llm=True, client=_fake_client(captured))
    assert run.mode == "none" and captured == []


def test_safety_module_is_isolated_from_ai_layer():
    tree = ast.parse(Path(safety_alerts.__file__).read_text())
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("anthropic" in m or "matchmaker" in m for m in imported)


def test_safety_templates_reject_unknown_venue():
    with pytest.raises(ValueError):
        safety_alerts.render("room_change", session_title="Keynote", venue="Building 9", room="A")


def _status_client(status: int, body: dict) -> anthropic.Anthropic:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    return anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=transport), max_retries=0)


def test_key_is_masked_to_last_four(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-secretvalue-f3a9")
    status = detect_key()
    assert status.present and status.masked == "sk-ant-…f3a9"
    assert "secretvalue" not in status.masked


def test_no_key_detected(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert not detect_key().present


def test_verify_key_accepts_and_rejects():
    ok = verify_key(_status_client(200, {"id": "claude-opus-5-5", "type": "model", "display_name": "Claude Opus 5.5",
                                         "created_at": "2026-01-01T00:00:00Z"}))
    bad = verify_key(_status_client(401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}))
    assert ok.ok and not bad.ok and "rejected" in bad.message


def test_roi_matches_locked_strategy_numbers():
    from meridian.roi import RoiInputs, compute
    base = compute(RoiInputs())                                 # 3 Platinum + 30% support cut
    assert base.support_savings == 126_000
    assert base.retained_revenue == 750_000 and base.payback_week == 5
    assert base.platinum_needed_to_break_even == 3
    assert round(base.churn_dollars) == 6_720_000
    portfolio = compute(RoiInputs(retention_mode="portfolio", renewal_lift_pct=1.5))
    assert portfolio.retained_revenue == 720_000
    support_only = compute(RoiInputs(platinum_retained=0))
    assert support_only.payback_week is None


# ---------------------------------------------------------------- Step 0: registration & consent
from meridian.registration import RegistrationForm, register  # noqa: E402


def _form(sponsor_channels, preferred="whatsapp", news=False, phone="+44 7700 900123"):
    return RegistrationForm(
        name="Pat Reviewer", email="pat@example.com", phone=phone, company="Example Co", role="CTO",
        industry="Technology", country="GB", preferred_channel=preferred, event_news_opt_in=news,
        topic_interests=("generative ai",), sponsor_channels=sponsor_channels,
    )


def _state_with(reg):
    return reconcile(SOURCES, AS_OF, extra_attendees=[reg.attendee], extra_events=list(reg.consent_events))


def test_registration_consent_flows_into_ledger_and_gate():
    reg = register(_form({"SP01": ("whatsapp",), "SP02": ()}), "R001")
    state = _state_with(reg)
    helix = evaluate(state, "R001", "SP01", HEALTHY)
    assert helix.allowed and helix.channel == "whatsapp"
    sentinel = evaluate(state, "R001", "SP02", HEALTHY)          # empty boxes = no
    assert not sentinel.allowed and "no consent" in sentinel.reason


def test_registration_channel_choice_wins_over_preferred_channel():
    state = _state_with(register(_form({"SP03": ("email",)}, preferred="whatsapp"), "R001"))
    d = evaluate(state, "R001", "SP03", HEALTHY)
    assert d.allowed and d.channel == "email"                    # only a channel they agreed to


def test_event_news_opt_in_is_not_sponsor_consent():
    state = _state_with(register(_form({}, news=True), "R001"))
    d = evaluate(state, "R001", "SP01", HEALTHY)
    assert not d.allowed and "general marketing opt-in only" in d.reason


def test_registration_validation():
    with pytest.raises(ValueError, match="mobile number"):
        register(_form({"SP01": ("sms",)}, preferred="email", phone=""), "R001")
    with pytest.raises(ValueError, match="valid work email"):
        register(RegistrationForm("Pat", "not-an-email", "", "Co", "CTO", "Technology", "GB",
                                  "email", False, (), {}), "R001")


def test_registered_attendee_reaches_matchmaker_without_pii():
    state = _state_with(register(_form({"SP05": ("whatsapp",)}), "R001"))
    run = run_matchmaking(state, "SP05", evaluate_sponsor(state, "SP05", HEALTHY), use_llm=False)
    payload = json.dumps(run.payload)
    assert "R001" in payload and "Pat Reviewer" not in payload and "pat@example.com" not in payload


def test_latched_breaker_stays_tripped_until_switched_off():
    from meridian.circuit_breaker import latched_breaker
    healthy_now = evaluate_breaker(SLACK, datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc))
    still_on = latched_breaker(True, "auto", healthy_now, "2026-11-20T13:00:00Z")  # complaints fell, no reset
    assert still_on.tripped and "automatically at 13:00" in still_on.reason   # the hour it tripped, not now
    assert not evaluate(STATE, "A001", "SP03", still_on).allowed
    reset = latched_breaker(False, None, healthy_now)
    assert not reset.tripped and evaluate(STATE, "A001", "SP03", reset).allowed


def test_custom_safety_template_requires_a_named_author():
    with pytest.raises(ValueError, match="your name"):
        safety_alerts.make_custom_template("Shuttle", "Shuttles suspended until 15:00.", "  ")
    t = safety_alerts.make_custom_template("Shuttle", "Shuttles suspended until 15:00.", "Dana Reyes")
    assert t["added_by"] == "Dana Reyes" and t["origin"] == "Human-written"
    assert t["text"] == "Shuttles suspended until 15:00."            # stored exactly as typed


def test_pass_through_estimate_keeps_week_5_payback():
    from meridian.roi import RoiInputs, compute, estimate_pass_through
    est = estimate_pass_through()
    assert est["rounded_usd"] == 15_000 and est["total_usd"] <= est["rounded_usd"]
    r = compute(RoiInputs(pass_through_costs=est["rounded_usd"]))
    assert r.net_benefit == 211_000 and r.payback_week == 5 and r.platinum_needed_to_break_even == 3
