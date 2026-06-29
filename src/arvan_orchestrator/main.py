"""Minimal entrypoint for the initial Arvan orchestrator skeleton."""

from __future__ import annotations

from arvan_orchestrator.settings import load_settings


def main() -> None:
    """Print safe startup status without exposing credentials."""

    settings = load_settings()
    write_status = "enabled" if settings.feature_gates.provider_writes_enabled else "disabled"
    print(f"Arvan orchestrator skeleton ready; provider writes are {write_status}.")


if __name__ == "__main__":
    main()
