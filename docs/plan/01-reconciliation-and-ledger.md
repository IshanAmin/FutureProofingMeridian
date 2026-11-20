# Step 1: Reconciliation & Consent Ledger

**Status: Done.** Tab ①. Code: `meridian/data_loader.py`, `meridian/ledger.py`, `data/`.

## Goal

Meridian runs six tools with no shared real-time state. Build one attendee view and one master
Consent Ledger that every later step reads from.

## Phases

| Phase | Scope | Output | Status |
|---|---|---|---|
| 1.1 Synthetic data | Realistic exports from all six tools, with the required edge cases built in | `data/*.json` (18 attendees, 6 sponsors, 25 consent events) | Done |
| 1.2 Loader | Read each tool's export as that vendor would provide it | `data_loader.py` | Done |
| 1.3 Attendee view | Merge identity, interests, channel preferences and unsubscribes per attendee | `build_attendees()` | Done |
| 1.4 Consent ledger | Collect grant/revoke events from four tools and resolve to one status per (attendee, sponsor) | `collect_consent_events()`, `resolve_consent()` | Done |
| 1.5 Send counts | Count sponsor messages per attendee across channels in the last 7 days | `count_recent_sponsor_sends()` | Done |
| 1.6 UI | Source counts, master ledger, unified attendee view, raw event timeline | Tab ① | Done |

## Phase 1.1: Synthetic data

| File | Holds |
|---|---|
| `registration_crm.json` | Identity, role, company, country, general marketing opt-in |
| `mobile_app.json` | Topic interests, push opt-in, in-app sponsor consent |
| `email_platform.json` | Unsubscribes, preference-center sponsor consent, sponsor sends |
| `sms_whatsapp_gateway.json` | Preferred channel, WhatsApp/SMS opt-in, YES/STOP keywords, sponsor sends |
| `badge_scan_vendor.json` | Sponsor list and buyer profiles, prior-year booth scans with a consent tick |
| `ops_slack.json` | Hourly opt-out/spam rollups and human flags (feeds step 4) |

Edge cases required for the prototype data (and where they live): general opt-in only (A002), granted then
revoked (A003), weekly cap reached (A004), international WhatsApp with valid consent (A001).

## Phase 1.4: Ledger rules (decisions)

| Rule | Decision |
|---|---|
| Conflicting records across tools | Latest event wins, ordered by timestamp |
| Booth scan without the consent tick | Not consent |
| Old consent | Expires after 365 days (`CONSENT_TTL_DAYS`) |
| General marketing opt-in | Never counts as sponsor consent |

## What went wrong and was fixed

The first generated Slack data had message text that disagreed with its own metrics
("14 opt-outs" against a metric of 12). The text is now generated from the metrics.
