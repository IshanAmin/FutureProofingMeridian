"""Tab ⓪ (step 0): the attendee's registration and consent screens, beside Meridian's internal view.

Left: a simulated browser showing exactly what the attendee sees. Right: the new record as it
lands in the ledger, with the consent gate's verdict per sponsor. Registrations live only in the
viewer's Streamlit session.
"""

import pandas as pd
import streamlit as st

from meridian.circuit_breaker import BreakerState
from meridian.gate import evaluate
from meridian.ledger import MeridianState
from meridian.registration import (CHANNELS, CONSENT_VERSION, Registration, RegistrationForm,
                                   consent_wording, describe_channels, next_attendee_id, register,
                                   validate)

SESSION_KEY = "registrations"
URL = "register.meridiansummit.example"
INDUSTRIES = ["Technology", "Financial Services", "Fintech", "Healthcare", "Retail", "Manufacturing",
              "Energy", "Telecommunications", "Logistics", "Media", "Insurance", "Public Sector", "Other"]
COUNTRIES = {"US": "United States", "GB": "United Kingdom", "IN": "India", "BR": "Brazil", "MX": "Mexico",
             "DE": "Germany", "FR": "France", "NG": "Nigeria", "AE": "United Arab Emirates",
             "SG": "Singapore", "JP": "Japan", "CA": "Canada", "AU": "Australia", "OTHER": "Other"}


def session_registrations() -> list[Registration]:
    return st.session_state.setdefault(SESSION_KEY, [])


def _browser_bar(path: str) -> None:
    st.markdown(f"""
<div style="border:1px solid rgba(128,128,128,.35);border-bottom:none;border-radius:12px 12px 0 0;
            background:rgba(128,128,128,.12);padding:8px 12px;display:flex;align-items:center;gap:12px;">
  <span style="display:flex;gap:6px;">
    <span style="width:12px;height:12px;border-radius:50%;background:#ff5f57;display:inline-block"></span>
    <span style="width:12px;height:12px;border-radius:50%;background:#febc2e;display:inline-block"></span>
    <span style="width:12px;height:12px;border-radius:50%;background:#28c840;display:inline-block"></span>
  </span>
  <span style="flex:1;background:rgba(128,128,128,.18);border-radius:6px;padding:4px 10px;
               font-family:ui-monospace,Menlo,monospace;font-size:13px;opacity:.85;">🔒 {URL}{path}</span>
</div>""", unsafe_allow_html=True)


def _registration_screen(state: MeridianState, platinum: dict[str, dict]) -> None:
    st.markdown("### Register for Meridian Summit 2027")
    st.caption("Simulation. Made-up details are fine; nothing is saved after you leave this page.")

    with st.form("registration"):
        name = st.text_input("Full name *")
        email = st.text_input("Work email *")
        c1, c2 = st.columns(2)
        company = c1.text_input("Company *")
        role = c2.text_input("Job title *", placeholder="e.g. CTO, VP Data Engineering")
        c3, c4 = st.columns(2)
        industry = c3.selectbox("Industry", INDUSTRIES)
        country = c4.selectbox("Country", list(COUNTRIES), format_func=COUNTRIES.get)
        phone = st.text_input("Mobile number", help="Only needed for WhatsApp or text messages.")
        preferred = st.radio("Preferred way to hear from us", list(CHANNELS),
                             format_func=CHANNELS.get, horizontal=True)
        topics = st.multiselect("Topics you care about", sorted(
            {t for sp in platinum.values() for t in sp["target_buyer_profile"]["topics"]}))

        st.markdown("---")
        st.markdown("**Stay in touch**")
        news = st.checkbox("Send me Meridian event news")

        st.markdown("**Sponsors who may contact you**")
        st.caption("Tick the channels you're happy with for each sponsor. Leave a sponsor empty to say no.")
        picks: dict[str, tuple[str, ...]] = {}
        for sid, sp in platinum.items():
            st.markdown(f"{sp['name']} <span style='opacity:.65;font-size:.88em'>· "
                        f"{', '.join(sp['target_buyer_profile']['topics'])}</span>", unsafe_allow_html=True)
            cols = st.columns(len(CHANNELS))
            picks[sid] = tuple(ch for col, (ch, label) in zip(cols, CHANNELS.items())
                               if col.checkbox(label, key=f"reg-{sid}-{ch}"))
        st.caption(f"Ticking a channel means: \"{consent_wording('[sponsor]', ['[the channels you tick]'])}\" "
                   f"(wording v{CONSENT_VERSION})")
        submitted = st.form_submit_button("Register", type="primary")

    if not submitted:
        return
    form = RegistrationForm(name=name, email=email, phone=phone, company=company, role=role,
                            industry=industry, country=country, preferred_channel=preferred,
                            event_news_opt_in=news, topic_interests=tuple(topics), sponsor_channels=picks)
    errors = validate(form)
    if errors:
        for e in errors:
            st.error(e)
        return
    regs = session_registrations()
    regs.append(register(form, next_attendee_id({r.attendee.attendee_id for r in regs})))
    st.session_state["show_confirmation"] = True
    st.rerun()


def _confirmation_screen(reg: Registration, platinum: dict[str, dict]) -> None:
    a = reg.attendee
    st.markdown("### ✅ You're registered")
    st.write(f"Thanks, {a.name.split()[0]}. A confirmation has been sent to **{a.email}**.")
    agreed = {ev.sponsor_id: ev.channels for ev in reg.consent_events}
    st.markdown("**Here's what you agreed to**")
    st.markdown(f"- Meridian event news: **{'Yes' if a.general_marketing_opt_in else 'No'}**")
    for sid, sp in platinum.items():
        if sid in agreed:
            st.markdown(f"- {sp['name']}: **Yes**, by {describe_channels(agreed[sid])}")
        else:
            st.markdown(f"- {sp['name']}: **No**")
    st.caption("You can stop any sponsor at any time by replying STOP or using the link in any message.")
    if st.button("Register another attendee"):
        st.session_state["show_confirmation"] = False
        st.rerun()


def _internal_view(state: MeridianState, platinum: dict[str, dict], breaker: BreakerState) -> None:
    regs = session_registrations()
    if not regs:
        st.info("No registrations yet. Fill in the form on the left.")
        return

    st.markdown("**New attendee records** (as they'd land in the registration CRM)")
    st.dataframe(pd.DataFrame([{
        "ID": r.attendee.attendee_id, "Name": r.attendee.name, "Email": r.attendee.email,
        "Company": r.attendee.company, "Role": r.attendee.role, "Country": r.attendee.country,
        "Preferred": r.attendee.preferred_channel, "Event news": r.attendee.general_marketing_opt_in,
    } for r in regs]), hide_index=True, width="stretch")

    st.markdown("**Consent events added to the ledger**")
    events = [ev for r in regs for ev in r.consent_events]
    if events:
        st.dataframe(pd.DataFrame([{
            "Attendee": ev.attendee_id, "Sponsor": state.sponsors[ev.sponsor_id]["name"],
            "Action": ev.action, "Channels": ", ".join(ev.channels or ()),
            "At (UTC)": ev.at.strftime("%Y-%m-%d %H:%M:%S"), "Ref": ev.ref,
        } for ev in events]), hide_index=True, width="stretch")
    else:
        st.caption("None. No sponsor boxes were ticked, so no sponsor may contact these attendees.")

    st.markdown("**Consent Gate verdicts**")
    st.dataframe(pd.DataFrame([{
        "Attendee": r.attendee.attendee_id, "Sponsor": sp["name"], "Channel": d.channel,
        "Gate": "✅ PASS" if d.allowed else "⛔ BLOCK", "Reason": d.reason,
    } for r in regs for sid, sp in platinum.items()
        for d in [evaluate(state, r.attendee.attendee_id, sid, breaker)]]),
        hide_index=True, width="stretch")
    st.caption("These attendees now also appear in tabs ① ledger, ② gate audit and ③ matchmaking.")

    if st.button("Clear demo registrations"):
        st.session_state[SESSION_KEY] = []
        st.session_state["show_confirmation"] = False
        st.rerun()


def render(state: MeridianState, breaker: BreakerState) -> None:
    platinum = {sid: sp for sid, sp in state.sponsors.items() if sp["tier"] == "platinum"}
    regs = session_registrations()
    show_confirmation = st.session_state.get("show_confirmation") and regs

    customer, internal = st.columns([3, 2], gap="large")
    with customer:
        st.markdown("#### 👁 CUSTOMER VIEW")
        st.caption("What an attendee sees when they register. Simulated browser.")
        _browser_bar("/confirmation" if show_confirmation else "/register")
        with st.container(border=True):
            if show_confirmation:
                _confirmation_screen(regs[-1], platinum)
            else:
                _registration_screen(state, platinum)

    with internal:
        st.markdown("#### 🔒 INTERNAL VIEW")
        st.caption("Meridian's side. Attendees never see this.")
        _internal_view(state, platinum, breaker)
