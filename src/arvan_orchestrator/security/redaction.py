"""Redaction helpers for sensitive provider credentials and diagnostic payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTION_PLACEHOLDER = "[REDACTED]"

_ARVAN_MACHINE_USER_KEY_RE = re.compile(r"(?i)\bapikey\s+[^\s,;\]\}\)\"']+")
_AUTHORIZATION_HEADER_RE = re.compile(
    r"(?im)^(?P<prefix>\s*authorization\s*[:=]\s*)(?P<quote>[\"']?)(?P<value>[^\r\n\"']+)(?P=quote)"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)"
    r"(?P<prefix>\b(?:token|password|private_key|secret|credential)\b\s*[:=]\s*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\r\n,}\]\"']+)"
    r"(?P=quote)"
)
_SECRET_KEY_PARTS = ("token", "password", "private_key", "secret", "credential")


def redact_text(value: str) -> str:
    """Redact secrets from free-form text before it is logged or displayed."""

    redacted = redact_arvan_machine_user_keys(value)
    redacted = redact_authorization_headers(redacted)
    return _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('prefix')}{match.group('quote')}{REDACTION_PLACEHOLDER}{match.group('quote')}",
        redacted,
    )


def redact_arvan_machine_user_keys(value: str) -> str:
    """Redact Arvan Machine User key values that begin with ``apikey ``."""

    return _ARVAN_MACHINE_USER_KEY_RE.sub(f"apikey {REDACTION_PLACEHOLDER}", value)


def redact_authorization_headers(value: str) -> str:
    """Redact Authorization header values from text containing HTTP-style headers."""

    return _AUTHORIZATION_HEADER_RE.sub(
        lambda match: f"{match.group('prefix')}{match.group('quote')}{REDACTION_PLACEHOLDER}{match.group('quote')}",
        value,
    )


def redact_secrets(value: Any) -> Any:
    """Recursively redact common secret-bearing keys from mappings and sequences.

    String values are also scanned for inline Machine User keys, Authorization headers, and common
    secret assignments.
    """

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            key: REDACTION_PLACEHOLDER if _is_secret_key(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_secrets(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SECRET_KEY_PARTS) or normalized == "authorization"
