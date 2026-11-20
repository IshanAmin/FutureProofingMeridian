"""Load the six disconnected tool exports exactly as each vendor would hand them over."""

import json
from pathlib import Path

from meridian.config import DATA_DIR

SOURCE_FILES = {
    "registration_crm": "registration_crm.json",
    "mobile_app": "mobile_app.json",
    "email_platform": "email_platform.json",
    "sms_whatsapp_gateway": "sms_whatsapp_gateway.json",
    "badge_scan_vendor": "badge_scan_vendor.json",
    "ops_slack": "ops_slack.json",
}


def load_sources(data_dir: Path = DATA_DIR) -> dict[str, dict]:
    sources = {}
    for name, filename in SOURCE_FILES.items():
        with open(data_dir / filename, encoding="utf-8") as fh:
            sources[name] = json.load(fh)
    return sources
