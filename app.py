"""Meridian Summit · Phase 1 wedge: Consent-Gated Sponsor Matchmaker (Platinum first).

Run:  streamlit run app.py
"""

import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from meridian import safety_alerts
from meridian.circuit_breaker import evaluate_breaker, latched_breaker
from meridian.config import AS_OF, MODEL, OPT_OUT_TRIP_RATE, WEEKLY_SPONSOR_CAP
from meridian import customer_view
from meridian.credentials import detect_key, verify_key
from meridian.data_loader import load_sources
from meridian.gate import evaluate_sponsor
from meridian.ledger import ledger_rows, reconcile
from meridian.matchmaker import run_matchmaking
from meridian.roi import CONTRACT_LOCK_WEEK, EVENT_WEEK, RoiInputs, compute, cumulative_timeline

st.set_page_config(page_title="Meridian · Consent-Gated Matchmaker", layout="wide")


@st.cache_data
def get_sources() -> dict:
    return load_sources()


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _flow_step(number: int, text: str) -> str:
    return (f'<div style="flex:1 1 120px;border:1.5px solid rgba(37,99,235,.55);border-radius:8px;'
            f'padding:8px 10px;font-size:0.85rem;line-height:1.35;background:rgba(37,99,235,.06);">'
            f'<div style="font-weight:700;opacity:.8;margin-bottom:2px;">{number}</div>{text}</div>')


_FLOW_ARROW = '<div style="flex:0 0 auto;align-self:center;font-size:22px;opacity:.7;">➜</div>'

# Tab ③: how a match brief is produced, as a small outlined flow chart.
MATCH_FLOW_HTML = (
    '<div style="border:1.5px solid rgba(128,128,128,.45);border-radius:10px;padding:10px;">'
    '<div style="font-weight:700;font-size:0.95rem;margin:0 0 8px 2px;">The workflow</div>'
    '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;">'
    + _FLOW_ARROW.join([
        _flow_step(1, '<b>Run gate</b><br><span style="font-size:22px;line-height:1;">↙</span>'),
        _flow_step(2, "Keep everyone who <b>said yes</b> to this sponsor"),
        _flow_step(3, "<b>Claude</b> compares each one to the sponsor's ideal buyer: job title, topics, industry"),
        _flow_step(4, "<b>Writes the brief</b>"),
    ])
    + "</div></div>"
)


def highlight_revoked(value) -> str:
    """Colour consent that no longer counts: red for revoked, yellow for expired."""
    if value in ("revoked", "revoke"):
        return "background-color: rgba(218, 54, 51, 0.30); font-weight: 600"
    if value == "expired":
        return "background-color: rgba(234, 179, 8, 0.35); font-weight: 600"
    return ""


def log_audit(rows: list[dict]) -> None:
    st.session_state.setdefault("audit_log", []).extend(rows)


def load_key_from_secrets() -> None:
    """Use the key from .streamlit/secrets.toml (local or Streamlit Cloud), so nobody has to export it.

    Streamlit also copies top-level secrets into environment variables, so the template's
    placeholder value must be removed explicitly or it would look like a real key.
    """
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except StreamlitSecretNotFoundError:
        key = ""
    if key and "PASTE" not in key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = key
    if "PASTE" in os.environ.get("ANTHROPIC_API_KEY", ""):
        del os.environ["ANTHROPIC_API_KEY"]


load_key_from_secrets()
sources = get_sources()
registrations = customer_view.session_registrations()   # step 0: live sign-ups in this session
state = reconcile(sources, AS_OF, extra_attendees=[r.attendee for r in registrations],
                  extra_events=[ev for r in registrations for ev in r.consent_events])
slack = sources["ops_slack"]["messages"]

# ---------------------------------------------------------------- sidebar: operator controls
# ---------------------------------------------------------------- AI connection (checked once per key)
key = detect_key()
key_checks = st.session_state.setdefault("key_checks", {})
if key.present and key.masked not in key_checks:
    with st.spinner("Verifying AI key with Anthropic…"):
        key_checks[key.masked] = verify_key()
key_result = key_checks.get(key.masked) if key.present else None

with st.sidebar:
    st.title("🎛️ Control room")
    st.subheader("Demo controls")
    st.caption("🧪 **Simulation:** the frozen clock and the replay slider act out one demo day. "
               "The stop button, the automatic shut-off and the AI backup are real controls "
               "Meridian's ops team would have in the live product.")
    st.caption(f"Demo day frozen at {AS_OF:%d %b %Y, %H:%M} UTC")

    rollup_times = [m["ts"] for m in slack if m.get("metrics")]
    replay_ts = st.select_slider(
        "Replay the day: hourly complaint reports",
        options=rollup_times,
        value=rollup_times[-2],
        format_func=lambda t: t[11:16] + " UTC",
        help="Each step is one hourly report of how many people unsubscribed or flagged sponsor messages "
             "as spam. Slide to 13:00 to see a bad hour trigger the automatic shut-off.",
    )
    # One latching switch. Complaints above the limit switch it on automatically (once per bad
    # hourly report); a person can also switch it on. Switching it off needs a named manual override.
    auto = evaluate_breaker(slack, _ts(replay_ts))
    st.session_state.setdefault("breaker_log", [])
    tripped_windows = st.session_state.setdefault("breaker_tripped_windows", set())

    def _log(action: str, by: str) -> None:
        st.session_state["breaker_log"].append({
            "Logged at (UTC)": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "Action": action,
            "By": by,
            "Report hour": f"{auto.window_ts[11:16]} UTC" if auto.window_ts else "-",
            "Complaint rate": f"{auto.latest_rate:.1%}" if auto.latest_rate is not None else "-",
        })

    if auto.tripped and auto.window_ts not in tripped_windows:
        tripped_windows.add(auto.window_ts)
        if not st.session_state.get("breaker_on"):
            st.session_state["breaker_on"] = True
            st.session_state["breaker_cause"] = "auto"
            st.session_state["breaker_trip_rate"] = auto.latest_rate
            st.session_state["breaker_trip_window"] = auto.window_ts
            _log("Tripped automatically", "System")

    def _toggle_flipped() -> None:
        if st.session_state["breaker_on"]:
            st.session_state["breaker_cause"] = "manual"
            st.session_state["override_error"] = None
            _log("Switched on by hand", "Operator")
        else:
            # Switching off is only allowed through the named manual override.
            st.session_state["breaker_on"] = True
            st.session_state["override_error"] = "To switch the breaker off, use Manual override and enter your name."

    def _manual_override() -> None:
        name = st.session_state.get("override_name", "").strip()
        if not name:
            st.session_state["override_error"] = "Enter your name to override the breaker."
            return
        st.session_state["override_error"] = None
        st.session_state["breaker_on"] = False
        st.session_state["breaker_cause"] = None
        st.session_state["override_by"] = name
        st.session_state["override_name"] = ""
        # Later bad reports can trip it again; the report on screen now counts as acknowledged.
        st.session_state["breaker_tripped_windows"] = {auto.window_ts} if auto.tripped else set()
        _log("Manual override: switched off", name)

    switched_on = st.toggle(
        "🛑 Circuit breaker", key="breaker_on", on_change=_toggle_flipped,
        help="ON means every sponsor message is stopped. It switches on by itself when complaints pass "
             f"{OPT_OUT_TRIP_RATE:.0%} in an hour, and anyone on ops can switch it on. Switching it off needs "
             "a manual override with the person's name, which is logged.",
    )
    cause = st.session_state.get("breaker_cause")
    breaker = latched_breaker(switched_on, cause, auto, st.session_state.get("breaker_trip_window"))

    limit = f"{OPT_OUT_TRIP_RATE:.0%}"
    if switched_on and cause == "auto":
        trip_at = st.session_state["breaker_trip_window"][11:16]
        st.error(f"⛔ **Sponsor messages OFF**\n\nThe circuit breaker tripped automatically: complaints reached "
                 f"{st.session_state['breaker_trip_rate']:.1%} in the {trip_at} UTC report (limit {limit}). "
                 "It stays off until someone uses Manual override.")
    elif switched_on:
        st.error("⛔ **Sponsor messages OFF**\n\nThe circuit breaker was switched on by hand.")
    elif auto.tripped:
        st.warning(f"⚠️ **Sponsor messages ON, breaker overridden**\n\nComplaints are {auto.latest_rate:.1%}, "
                   f"above the {limit} limit, but {st.session_state.get('override_by', 'a person')} "
                   "overrode the breaker.")
    else:
        st.success(f"✅ **Sponsor messages ON**\n\nComplaints {auto.latest_rate:.1%} in the last hour "
                   f"(breaker trips at {limit}).")

    if switched_on:
        with st.form("breaker_override", border=True):
            st.markdown("**Manual override**")
            st.text_input("Your name (recorded in the audit log)", key="override_name")
            st.form_submit_button("Switch breaker off", on_click=_manual_override)
        if st.session_state.get("override_error"):
            st.error(st.session_state["override_error"])
    n_logged = len(st.session_state["breaker_log"])
    if n_logged:
        st.caption(f"Breaker log: {n_logged} entr{'y' if n_logged == 1 else 'ies'}. Full log in tab ④.")

    has_creds = key.present
    engine = st.radio(
        "Who ranks attendees for sponsors",
        [f"Claude AI ({MODEL})", "Backup: simple scoring rules"],
        index=0 if has_creds else 1,
        help="If the AI is unavailable, simple rules (job title, shared topics) rank attendees instead, "
             "so the product and the demo never depend on the AI being up.",
    )
    use_llm = engine.startswith("Claude")
    if use_llm and not has_creds:
        st.warning("No AI key found, so the backup scoring rules will be used.")

# Small AI-connection box at the bottom of the Control room.
with st.sidebar:
    with st.container(border=True):
        if not key.present:
            st.caption("🔴 **AI connection:** no key loaded, so the backup scoring rules are used. "
                       "Add `ANTHROPIC_API_KEY` to `.streamlit/secrets.toml` and restart.")
        elif key_result.ok:
            st.caption(f"🟢 **AI connection:** key `{key.masked}` accepted · {MODEL} available")
        else:
            st.caption(f"🟠 **AI connection:** key `{key.masked}` not working ({key_result.message})")
        if key.present:
            st.button("Re-check key", type="tertiary", on_click=lambda: key_checks.pop(key.masked, None),
                      help="Verify the AI key with Anthropic again (uses no tokens).")

st.title("Meridian Summit · Consent-Gated Sponsor Matchmaker")
st.caption("Phase 1 · Platinum sponsors only · No AI runs without consent")

tab_register, tab_ledger, tab_gate, tab_match, tab_ops, tab_roi = st.tabs([
    "⓪ Customer View: Registration & Consent",
    "① Reconciliation & Consent Ledger",
    "② Consent Gate & Audit Log",
    "③ Sponsor Matchmaking",
    "④ Rollback & Safety",
    "⑤ ROI Simulator",
])

# ---------------------------------------------------------------- 1. reconciliation
with tab_register:
    customer_view.render(state, breaker)

with tab_ledger:
    st.subheader("Six tools, no shared state → one attendee view and one consent ledger")
    counts = pd.DataFrame([
        {"Tool": "registration_crm", "Records": len(sources["registration_crm"]["attendees"]),
         "Contributes": "identity, role, company, general marketing opt-in"},
        {"Tool": "mobile_app", "Records": len(sources["mobile_app"]["profiles"]),
         "Contributes": "topic interests, push opt-in, in-app sponsor consent"},
        {"Tool": "email_platform", "Records": len(sources["email_platform"]["subscribers"]),
         "Contributes": "unsubscribes, preference-center sponsor consent, sponsor sends"},
        {"Tool": "sms_whatsapp_gateway", "Records": len(sources["sms_whatsapp_gateway"]["channel_preferences"]),
         "Contributes": "preferred channel, WhatsApp/SMS opt-in, YES/STOP keywords, sponsor sends"},
        {"Tool": "badge_scan_vendor", "Records": len(sources["badge_scan_vendor"]["booth_scans"]),
         "Contributes": "sponsor master + buyer profiles, prior-year booth scans with consent tick"},
        {"Tool": "ops_slack", "Records": len(slack),
         "Contributes": "hourly opt-out/spam rollups feeding the circuit breaker"},
    ])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sources merged", len(counts))
    c2.metric("Attendees", len(state.attendees))
    c3.metric("Consent events", len(state.consent_events))
    c4.metric("Valid sponsor consents", sum(cs.is_valid for cs in state.consent.values()))
    st.dataframe(counts, hide_index=True, width="stretch")

    st.markdown("#### Master Consent Ledger")
    st.caption("Latest event per (attendee, sponsor) wins across all four tools that record consent. "
               "Grants older than 365 days expire.")
    st.dataframe(pd.DataFrame(ledger_rows(state)).style.map(highlight_revoked, subset=["Consent Status"]),
                 hide_index=True, width="stretch")

    with st.expander("Unified attendee view: everything about each person in one row."):
        st.dataframe(pd.DataFrame([{
            "ID": a.attendee_id, "Name": a.name, "Role": a.role, "Company": a.company,
            "Country": a.country, "General marketing opt-in": a.general_marketing_opt_in,
            "Preferred channel": a.preferred_channel,
            "Opted in on preferred channel": a.channel_opt_in.get(a.preferred_channel, False),
            "Sponsor sends (7d)": state.sponsor_sends_7d.get(a.attendee_id, 0),
            "Topics": ", ".join(a.topic_interests),
        } for a in state.attendees.values()]), hide_index=True, width="stretch")

    with st.expander("Raw consent event timeline (every grant/revoke from every tool)"):
        st.dataframe(pd.DataFrame([{
            "At": ev.at.strftime("%Y-%m-%d %H:%M"), "Attendee": ev.attendee_id,
            "Sponsor": ev.sponsor_id, "Action": ev.action, "Source": ev.source, "Ref": ev.ref,
        } for ev in state.consent_events]).style.map(highlight_revoked, subset=["Action"]),
            hide_index=True, width="stretch")

# ---------------------------------------------------------------- 2. gate + audit
with tab_gate:
    st.subheader("Deterministic Consent Gate")
    code_col, note_col = st.columns([3, 2], vertical_alignment="center")
    code_col.code(
        "allowed = breaker_ok and sponsor_in_rollout \\\n"
        "      and sponsor_specific_consent == True \\\n"
        "      and channel_opt_in == True \\\n"
        f"      and weekly_sponsor_sends < {WEEKLY_SPONSOR_CAP}",
        language="python",
    )
    note_col.markdown(
        """
<div style="display:flex;align-items:center;gap:10px;">
  <span style="font-size:28px;line-height:1;">⬅</span>
  <div style="border:1.5px solid rgba(128,128,128,.55);border-radius:8px;padding:8px 12px;
              font-size:0.88rem;line-height:1.4;">
    <strong>It's not AI that makes the decision.</strong><br>
    It's plain rules written as code, and hence it gives the same answer every time,
    since the checks are hard-coded.
  </div>
</div>""",
        unsafe_allow_html=True,
    )
    sponsor_id = st.selectbox(
        "Evaluate every attendee against sponsor",
        list(state.sponsors),
        format_func=lambda s: f"{state.sponsors[s]['name']} ({state.sponsors[s]['tier']})",
    )
    decisions = evaluate_sponsor(state, sponsor_id, breaker)
    # Log automatically, but only when this sponsor's outcomes are new (first view, or something changed
    # such as the breaker or a new registration), so page refreshes don't add duplicate rows.
    outcome = (sponsor_id, tuple((d.attendee_id, d.allowed, d.reason) for d in decisions))
    logged = st.session_state.setdefault("gate_outcomes_logged", set())
    if outcome not in logged:
        logged.add(outcome)
        log_audit([d.as_audit_row() for d in decisions])

    passed = sum(d.allowed for d in decisions)
    c1, c2 = st.columns(2)
    c1.metric("Passed", passed)
    c2.metric("Blocked", len(decisions) - passed)

    st.markdown("#### Decision table")
    audit_df = pd.DataFrame([d.as_audit_row() for d in decisions])
    st.dataframe(
        audit_df.style.apply(
            lambda row: ["background-color: rgba(46,160,67,0.18)" if row["allowed"]
                         else "background-color: rgba(218,54,51,0.12)"] * len(row), axis=1),
        hide_index=True, width="stretch",
    )

    st.markdown("#### Session audit log")
    log = st.session_state.get("audit_log", [])
    if log:
        log_df = pd.DataFrame(log)
        st.dataframe(log_df, hide_index=True, width="stretch")
        st.download_button("Download audit log (CSV)", log_df.to_csv(index=False),
                           "consent_gate_audit.csv", "text/csv")
    else:
        st.caption("Empty. Gate decisions are added here automatically when you pick a sponsor "
                   "or generate a match brief.")

# ---------------------------------------------------------------- 3. matchmaking
with tab_match:
    heading_col, flow_col = st.columns([1, 3], vertical_alignment="center")
    heading_col.subheader("Marcus Demo for Platinum Sponsors")
    flow_col.markdown(MATCH_FLOW_HTML, unsafe_allow_html=True)
    platinum = [s for s, sp in state.sponsors.items() if sp["tier"] == "platinum"]
    match_sponsor = st.selectbox("Sponsor", platinum,
                                 format_func=lambda s: state.sponsors[s]["name"], key="match_sponsor")
    sponsor = state.sponsors[match_sponsor]
    st.caption("Target buyer: " + ", ".join(sponsor["target_buyer_profile"]["roles"])
               + " · Topics: " + ", ".join(sponsor["target_buyer_profile"]["topics"]))

    if breaker.tripped:
        st.error("Sponsor outbound is halted. Matchmaking is disabled and the app has degraded to "
                 "the static pull-only sponsor directory (see tab ④).")
    elif st.button("Run gate → generate match brief", type="primary"):
        gate = evaluate_sponsor(state, match_sponsor, breaker)
        log_audit([d.as_audit_row() for d in gate])
        with st.spinner("Matching consented attendees…"):
            run = run_matchmaking(state, match_sponsor, gate, use_llm=use_llm)
        st.session_state["last_run"] = (run, gate)

    if (last := st.session_state.get("last_run")) and last[0].sponsor_id == match_sponsor and not breaker.tripped:
        run, gate = last
        passed = [d for d in gate if d.allowed]
        c1, c2, c3 = st.columns(3)
        c1.metric("Attendees evaluated by gate", len(gate))
        c2.metric("Passed to matchmaker", len(passed))
        c3.metric("Engine", {"llm": f"Claude · {MODEL}", "offline": "Offline scorer",
                             "none": "No call"}[run.mode])
        if run.note:
            st.info(run.note)
        if run.dropped_ids:
            st.warning(f"Model returned ids not in the consented set; dropped: {run.dropped_ids}")

        if run.matches:
            # Names are joined back locally after matching; they were never sent to the model.
            st.dataframe(pd.DataFrame([{
                "Fit": m.fit_score,
                "Attendee": state.attendees[m.attendee_id].name,
                "Role": state.attendees[m.attendee_id].role,
                "Company": state.attendees[m.attendee_id].company,
                "Channel": state.attendees[m.attendee_id].preferred_channel,
                "Why": m.rationale,
                "Suggested opener (needs sponsor approval before send)": m.suggested_opener,
            } for m in run.matches]), hide_index=True, width="stretch")

        with st.expander("Exactly what the matchmaker saw (minimized: no names, emails or companies)"):
            st.json(run.payload)
        with st.expander(f"Blocked by gate before matching ({len(gate) - len(passed)})"):
            st.dataframe(pd.DataFrame([{"Attendee": d.attendee_name, "Reason": d.reason}
                                       for d in gate if not d.allowed]),
                         hide_index=True, width="stretch")

# ---------------------------------------------------------------- 4. rollback + safety
with tab_ops:
    st.subheader("Circuit breaker")
    rollups = [{
        "Window end (UTC)": m["ts"][11:16],
        "Sent": m["metrics"]["sent"],
        "Opt-outs": m["metrics"]["opt_outs"],
        "Spam reports": m["metrics"]["spam_reports"],
        "Rate %": round(100 * (m["metrics"]["opt_outs"] + m["metrics"]["spam_reports"]) / m["metrics"]["sent"], 2),
    } for m in slack if m.get("metrics") and _ts(m["ts"]) <= _ts(replay_ts)]
    roll_df = pd.DataFrame(rollups)
    roll_df["Trip threshold %"] = OPT_OUT_TRIP_RATE * 100
    st.line_chart(roll_df, x="Window end (UTC)", y=["Rate %", "Trip threshold %"])
    st.dataframe(pd.DataFrame([{"Time": m["ts"][11:16], "User": m["user"], "Message": m["text"]}
                               for m in slack if _ts(m["ts"]) <= _ts(replay_ts)]),
                 hide_index=True, width="stretch")

    st.subheader("Circuit breaker log")
    st.caption("Every automatic trip, manual switch-on and named manual override in this session.")
    breaker_log = st.session_state.get("breaker_log", [])
    if breaker_log:
        log_df = pd.DataFrame(breaker_log)
        st.dataframe(log_df, hide_index=True, width="stretch")
        st.download_button("Download breaker log (CSV)", log_df.to_csv(index=False), "circuit_breaker_log.csv", "text/csv")
    else:
        st.caption("Empty. Slide the replay to 13:00 to trip the breaker.")

    st.subheader("Degraded mode: static pull-only sponsor directory")
    st.caption("Shown in the mobile app when outbound is halted. Attendees browse; nothing is pushed.")
    st.dataframe(pd.DataFrame([{"Sponsor": s["name"], "Tier": s["tier"], "Booth": s["booth"]}
                               for s in state.sponsors.values()]), hide_index=True, width="stretch")

    st.subheader("Safety alerts (outside the AI layer)")
    st.caption("Human-written templates only. No model call, not affected by the circuit breaker, "
               "fields restricted to enumerated venues and shelter points.")
    template_id = st.selectbox("Template", list(safety_alerts.TEMPLATES))
    if template_id == "severe_weather_shelter":
        fields = {"shelter_point": st.selectbox("Shelter point", list(safety_alerts.SHELTER_POINTS))}
    else:
        fields = {
            "session_title": st.text_input("Session title (from schedule system)", "Opening Keynote"),
            "venue": st.selectbox("Venue", list(safety_alerts.VENUES)),
            "room": st.text_input("Room", "Ballroom A"),
        }
    st.code(safety_alerts.render(template_id, **fields), language=None)

# ---------------------------------------------------------------- 5. ROI simulator
with tab_roi:
    st.subheader("Phase 1 payback against the $650K fee")
    st.caption("The CFO asked for support costs down 30%. That alone can't pay back the fee; "
               "retaining sponsor revenue can. Every input is editable.")

    left, right = st.columns([1, 2])
    with left:
        fee = st.number_input("Phase 1 fee ($) - (Paid to Future Proofing)", value=650_000, step=25_000)
        pass_through = st.number_input("Messaging + inference pass-through ($, estimate)", value=0, step=5_000,
                                       help="Passed through to Meridian on top of the fee. Set your estimate.")
        st.markdown("**Support lever**")
        payroll = st.number_input("Event-week support payroll ($)", value=420_000, step=10_000)
        support_pct = st.slider("Support cost reduction (%)", 0, 60, 30)
        st.markdown("**Sponsor retention lever**")
        mode = st.radio("Model retention as", ["Platinum sponsors retained", "Portfolio renewal-rate lift"],
                        horizontal=True)
        platinum_n = st.slider("Additional Platinum sponsors retained ($250K each)", 0, 10, 3,
                               disabled=mode != "Platinum sponsors retained")
        lift = st.slider("Renewal-rate lift on $48M sponsor book (pp)", 0.0, 5.0, 1.5, 0.25,
                         disabled=mode != "Portfolio renewal-rate lift")

    inputs = RoiInputs(
        phase1_fee=fee, pass_through_costs=pass_through,
        support_payroll=payroll, support_reduction_pct=support_pct,
        retention_mode="platinum" if mode.startswith("Platinum") else "portfolio",
        platinum_retained=platinum_n, renewal_lift_pct=lift,
    )
    r = compute(inputs)

    with right:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Year-1 benefit", f"${r.total_benefit:,.0f}")
        net_sign = "-" if r.net_benefit < 0 else ""
        m2.metric("Net vs fee", f"{net_sign}${abs(r.net_benefit):,.0f}", delta=f"{r.roi_pct:.0f}% ROI")
        m3.metric("Payback multiple", f"{r.payback_multiple:.2f}×")
        m4.metric("Payback", {CONTRACT_LOCK_WEEK: f"Week {CONTRACT_LOCK_WEEK} (contract lock)",
                              EVENT_WEEK: f"Week {EVENT_WEEK} (event week)"}.get(r.payback_week, "Not in Year 1"))

        if r.payback_week is None:
            st.error(f"Does not pay back. Shortfall ${-r.net_benefit:,.0f}.")
        else:
            st.success(f"Pays back by week {r.payback_week}.")

        st.line_chart(pd.DataFrame(cumulative_timeline(inputs, r)), x="Week",
                      y=["Cumulative benefit", "Phase 1 cost"])

        st.markdown(
            f"- **Support alone:** ${r.support_savings:,.0f} covers **{r.support_only_coverage_pct:.0f}%** "
            f"of the fee, and only at event week (week {EVENT_WEEK}).\n"
            f"- **Sponsor retention:** ${r.retained_revenue:,.0f} recovers **{r.churn_recovered_pct:.1f}%** "
            f"of the ${r.churn_dollars / 1e6:.2f}M lost to the 14% renewal drop, booked at contract lock "
            f"(week {CONTRACT_LOCK_WEEK}).\n"
            f"- **Break-even:** with the support savings above, Meridian needs "
            f"**{r.platinum_needed_to_break_even} retained Platinum sponsor(s)** to cover the fee."
        )
