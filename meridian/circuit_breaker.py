"""Automated circuit breaker + manual global kill switch for sponsor outbound.

Trips when the latest hourly (opt-outs + spam reports) / sent rate in #sponsor-comms-monitor
exceeds OPT_OUT_TRIP_RATE. When tripped, every gate decision fails closed and the app
degrades to a static, pull-only sponsor directory. Safety alerts are not routed through here.
"""

from dataclasses import dataclass
from datetime import datetime

from meridian.config import OPT_OUT_TRIP_RATE


@dataclass(frozen=True)
class BreakerState:
    tripped: bool
    reason: str
    latest_rate: float | None
    window_ts: str | None
    manual_kill: bool

    @property
    def outbound_allowed(self) -> bool:
        return not self.tripped


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate_breaker(slack_messages: list[dict], through: datetime, kill_switch: bool = False,
                     threshold: float = OPT_OUT_TRIP_RATE) -> BreakerState:
    rollups = [m for m in slack_messages if m.get("metrics") and _ts(m["ts"]) <= through]
    latest = max(rollups, key=lambda m: m["ts"]) if rollups else None

    rate = None
    if latest:
        mx = latest["metrics"]
        rate = (mx["opt_outs"] + mx["spam_reports"]) / mx["sent"] if mx["sent"] else 0.0

    if kill_switch:
        return BreakerState(True, "Manual global kill switch engaged", rate,
                            latest["ts"] if latest else None, True)
    if rate is not None and rate > threshold:
        return BreakerState(True, f"Auto-tripped: opt-out/spam rate {rate:.2%} > {threshold:.0%}",
                            rate, latest["ts"], False)
    return BreakerState(False, "Healthy", rate, latest["ts"] if latest else None, False)
