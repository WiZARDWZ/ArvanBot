"""Application settings for the ArvanCloud orchestrator.

Provider writes intentionally fail closed until controlled write validation is complete.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HttpSettings:
    """HTTP client defaults from Agent.md section 4."""

    connect_timeout_seconds: int = 10
    read_timeout_seconds: int = 30
    write_timeout_seconds: int = 30
    pool_timeout_seconds: int = 10
    max_connections: int = 20
    max_keepalive_connections: int = 10


@dataclass(frozen=True)
class ArvanSettings:
    """ArvanCloud provider settings with write operations disabled by default."""

    base_url: str = "https://napi.arvancloud.ir/ecc/v1"
    authorization_value_env: str = "ARVAN_MU_KEY"
    default_region: str = "ir-thr-c2"
    writes_enabled: bool = False
    write_disable_reason: str = (
        "Provider write functionality is disabled until controlled validation is complete."
    )


@dataclass(frozen=True)
class AccountPoolSettings:
    """Authorized account pool controls."""

    mode: str = "authorized_multi_tenant"
    allow_cross_account_handover: bool = False
    approval_reference: str | None = None


@dataclass(frozen=True)
class Settings:
    """Top-level application settings."""

    arvan: ArvanSettings = field(default_factory=ArvanSettings)
    account_pool: AccountPoolSettings = field(default_factory=AccountPoolSettings)
    http: HttpSettings = field(default_factory=HttpSettings)

    @property
    def arvan_mu_key(self) -> str | None:
        """Return the injected Machine User key, if present; never provide a fallback secret."""

        return os.getenv(self.arvan.authorization_value_env)


def load_settings(path: str | Path | None = None) -> Settings:
    """Load skeleton settings, defaulting to fail-closed in-memory settings.

    The initial skeleton intentionally avoids requiring optional runtime dependencies merely to start.
    Full YAML validation will be added with the settings implementation phase.
    """

    settings_path = Path(path or os.getenv("ARVAN_SETTINGS_FILE", "config/settings.example.yaml"))
    if not settings_path.exists():
        return Settings()

    raw_data = _parse_simple_yaml(settings_path)
    return Settings(
        arvan=ArvanSettings(**raw_data.get("arvan", {})),
        account_pool=AccountPoolSettings(**raw_data.get("account_pool", {})),
        http=HttpSettings(**raw_data.get("http", {})),
    )


def _parse_simple_yaml(path: Path) -> dict[str, dict[str, Any]]:
    """Parse the limited two-level example YAML used by the initial skeleton."""

    data: dict[str, dict[str, Any]] = {}
    current_section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1]
            data[current_section] = {}
            continue
        if current_section is None or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        data[current_section][key] = _coerce_scalar(value.strip())
    return data


def _coerce_scalar(value: str) -> Any:
    """Coerce simple YAML scalar values from the example settings file."""

    if value in {"true", "false"}:
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return value
