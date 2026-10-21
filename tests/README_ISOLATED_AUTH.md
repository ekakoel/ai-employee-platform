# Isolated auth tests (Job 85)

These modules can register process-wide `sys.addaudithook` SQLite guards.
They are **ignored by default** (`pytest.ini`).

| File | Notes |
|------|--------|
| `test_auth_p0_isolated.py` | P0 memory-only auth |
| `test_auth_sessions_isolated.py` | Session lifecycle + audit hook |
| `test_auth_sessions_postgres.py` | Imports sessions_isolated — also ignored |

## Main suite

```bash
pytest -q -m "not integration"
```

## Isolated runs (enable guards)

```bash
# Windows PowerShell
$env:AUTH_ISOLATED_GUARDS="1"
pytest -q tests/test_auth_p0_isolated.py --tb=short
pytest -q tests/test_auth_sessions_isolated.py --tb=short

# Linux/macOS
AUTH_ISOLATED_GUARDS=1 pytest -q tests/test_auth_p0_isolated.py --tb=short
```

Guards only register when `AUTH_ISOLATED_GUARDS=1`, so accidental imports
cannot poison the main suite.
