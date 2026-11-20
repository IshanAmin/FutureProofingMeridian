# Step 0: Attendee Registration & Consent (customer view)

**Status: Done.** Tab ⓪. Code: `meridian/registration.py`, `meridian/customer_view.py`.

## Goal

Show the customer side: how an attendee registers for Meridian Summit and gives (or doesn't give)
consent to hear from a specific sponsor such as Helix Cloud. The screens appear inside a browser
outline, so it is obvious this is what the attendee sees. It is a simulation, not a real website.

**Why it matters:** Ines Okafor (GC): "No sponsor message reaches an attendee without valid,
sponsor-specific consent." Steps 1–2 enforce consent; step 0 shows where it comes from.

## Phases

| Phase | Scope | Output | Status |
|---|---|---|---|
| 0.1 Decisions | Settle the consent rules before writing code | Decisions below | Done |
| 0.2 Data model | A registration becomes an attendee record plus per-sponsor consent events that feed the existing ledger and gate | `registration.py`; changes to `ledger.py`, `gate.py`; 5 tests | Done |
| 0.3 Registration screen | Browser outline (`register.meridiansummit.example`) with the registration form and the consent section | New tab ⓪ "Customer View" | Done |
| 0.4 Confirmation + internal view | Confirmation screen showing what the attendee agreed to; beside it, the internal view showing the new record in the ledger and the gate's verdict per sponsor | Tab ⓪ | Done |
| 0.5 Wrap-up | Tests, headless run-through, README and plan docs | This doc, README | Done |

## Phase 0.1: Decisions

| Question | Decision | Why |
|---|---|---|
| Consent per sponsor? | Yes. One block per Platinum sponsor, with Email / WhatsApp / SMS boxes | GC's sponsor-specific rule |
| Pre-ticked boxes? | None. Empty means no | Consent must be an active choice |
| Meridian event news | A separate, unticked opt-in. It never counts as sponsor consent | Matches the existing general-opt-in edge case (A002) |
| Registration channel choice vs general channel settings? | The choice made at registration wins (decided earlier) | It is the newest, most specific choice |
| Which channel does the gate use? | Preferred channel if agreed for that sponsor, otherwise the first agreed channel | Never contact someone on a channel they didn't pick |
| Where is the submission stored? | In the demo session only. It appears in the ledger, gate and matchmaking for that viewer, and is gone when the session ends | Nothing personal is saved to disk; reviewers on a hosted link don't see each other's entries |
| Consent wording | Draft, versioned, shown on the screen next to the boxes | Needs GC sign-off before real use |

## Phase 0.3: What the attendee sees

```
┌─ ● ● ●  🔒 register.meridiansummit.example ───────────────────┐
│  Register for Meridian Summit 2027                            │
│  Name · Work email · Company · Job title · Country · Mobile   │
│  Preferred channel: (•) Email ( ) WhatsApp ( ) SMS            │
│                                                               │
│  Stay in touch                                                │
│  [ ] Send me Meridian event news                              │
│                                                               │
│  Sponsors who may contact you  (leave empty to say no)        │
│  Helix Cloud        [ ] Email  [ ] WhatsApp  [ ] SMS          │
│  Sentinel Security  [ ] Email  [ ] WhatsApp  [ ] SMS          │
│  …                                                            │
│  "Yes, <sponsor> may contact me by <channels>. I can stop     │
│   at any time."                                               │
│                                              [ Register ]     │
└───────────────────────────────────────────────────────────────┘
```

## Phase 0.2: Data model

- `registration.py` turns the form into an `Attendee` plus one consent `grant` per sponsor with at least
  one channel ticked. Each grant records its channels, timestamp and wording version.
- `reconcile()` accepts these, so registrations enter the same ledger as the six tools.
- The gate uses only channels the attendee agreed to for that sponsor. Every other check still applies.

**Tests:**
- `test_registration_consent_flows_into_ledger_and_gate`
- `test_registration_channel_choice_wins_over_preferred_channel`
- `test_event_news_opt_in_is_not_sponsor_consent`
- `test_registration_validation`
- `test_registered_attendee_reaches_matchmaker_without_pii`

## Phases 0.3–0.4: Screens

- **Customer view (left):** a browser outline. The URL bar changes from `/register` to `/confirmation`.
  - The registration form validates required fields, the email, and a mobile number for WhatsApp/SMS.
  - The confirmation screen lists exactly what the attendee agreed to, sponsor by sponsor.
- **Internal view (right):** the new attendee records, the consent events added to the ledger, and the
  gate verdict for every new attendee × Platinum sponsor. New attendees also appear in tabs ①–③.

**Headless run-through, checked:** empty-form errors → registration → confirmation (Helix: Yes by WhatsApp,
Lumen: Yes by Email, others: No) → ledger grows from 25 to 27 events → gate PASS for Helix (WhatsApp) and
Lumen (email), BLOCK for the rest → back to the form.

## Demo script (1 minute)

1. Tab ⓪: register yourself and tick **Helix Cloud → WhatsApp** only.
2. The confirmation screen shows Helix: Yes, everyone else: No.
3. On the right, Helix shows **PASS on WhatsApp**; every other sponsor shows **BLOCK: no consent**.
4. Tab ③: run the Helix Cloud match brief. You're in it, and "Exactly what the matchmaker saw" has no name or email.

## Out of scope (prototype)

- Real sign-in or badge identity.
- Changing consent after registration. The existing STOP flows (WhatsApp, email preference center) already cover revocation in the data.
- WhatsApp template approval by Meta, and double opt-in where local law requires it.
- Saving submissions across sessions.
