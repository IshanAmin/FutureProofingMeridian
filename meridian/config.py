"""Single place for every tunable the CRO, GC or on-call engineer might ask about."""

from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Fixed "now" so the demo and tests are reproducible against the synthetic data.
AS_OF = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

# Consent rules (Ines Okafor, GC)
CONSENT_TTL_DAYS = 365          # a sponsor consent older than this is treated as expired
WEEKLY_SPONSOR_CAP = 2          # gate requires sends_in_last_7_days < this value
CAP_WINDOW_DAYS = 7

# Rollback plan
OPT_OUT_TRIP_RATE = 0.02        # (opt-outs + spam reports) / sent in the latest hourly window
ROLLOUT_TIERS = frozenset({"platinum"})  # staged rollout: Platinum sponsors only in Phase 1

# Model
MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
