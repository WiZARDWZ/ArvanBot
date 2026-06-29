# Arvan Orchestrator

Initial Python skeleton for a deterministic, observable, recoverable, and testable ArvanCloud IaaS orchestrator.

## Safety defaults

- No real credentials are committed.
- Provider write functionality is disabled by default (`arvan.writes_enabled: false`).
- API details that have not been live validated must be marked `NEEDS_LIVE_VALIDATION` before production use.
- Machine User keys must be injected from a secret manager or environment variable and redacted from logs.

## Layout

- `config/settings.example.yaml` — safe example configuration.
- `src/arvan_orchestrator/settings.py` — typed settings loader with fail-closed write defaults.
- `src/arvan_orchestrator/main.py` — minimal CLI entrypoint that reports write status.
- `tests/` — placeholders for unit, contract, integration, and fixture assets.

## Quick start

```bash
python -m arvan_orchestrator.main
```

Set `PYTHONPATH=src` when running directly from a checkout without installing the package.
