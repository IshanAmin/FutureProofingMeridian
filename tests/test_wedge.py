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
