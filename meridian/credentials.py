"""Detect and verify Anthropic credentials without ever exposing the key itself."""

import os
from dataclasses import dataclass

from meridian.config import MODEL

ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


@dataclass(frozen=True)
class KeyStatus:
    present: bool
    env_var: str | None
    masked: str | None       # e.g. "sk-ant-…f3a9" (last 4 characters only)


@dataclass(frozen=True)
class Verification:
    ok: bool
    message: str


def detect_key() -> KeyStatus:
    for var in ENV_VARS:
        value = os.environ.get(var, "").strip()
        if value:
            prefix = "sk-ant-" if value.startswith("sk-ant-") else ""
            return KeyStatus(True, var, f"{prefix}…{value[-4:]}")
    return KeyStatus(False, None, None)


def verify_key(client=None) -> Verification:
    """Look up the model's metadata: confirms the key and model access, uses no tokens."""
    import anthropic

    try:
        client = client or anthropic.Anthropic()
        client.models.retrieve(MODEL, timeout=10)
        return Verification(True, f"Key accepted · {MODEL} available")
    except anthropic.AuthenticationError:
        return Verification(False, "Key rejected (invalid or revoked)")
    except anthropic.PermissionDeniedError:
        return Verification(False, "Key valid but lacks permission")
    except anthropic.NotFoundError:
        return Verification(False, f"Key valid but {MODEL} is not available to it")
    except anthropic.APIConnectionError:
        return Verification(False, "Could not reach the Anthropic API (network)")
    except anthropic.APIStatusError as exc:
        return Verification(False, f"API error {exc.status_code}")
