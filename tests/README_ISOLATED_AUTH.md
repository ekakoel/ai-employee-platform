# Isolated auth tests (Job 85)

These modules register **process-wide** `sys.addaudithook` guards that block
any file-backed SQLite connection. They must **not** be collected with the
main suite.

| File | Guard message |
|------|----------------|
| `test_auth_p0_isolated.py` | P0 tests cannot open any file-backed SQLite database |
| `test_auth_sessions_isolated.py` | Session tests must never open workspace SQLite files |

## Default suite (safe)

```bash
pytest -q -m "not integration"
# pytest.ini already ignores the two files above
```

## Run isolated suites (separate process)

```bash
pytest -q tests/test_auth_p0_isolated.py --tb=short
pytest -q tests/test_auth_sessions_isolated.py --tb=short
```

Do not combine them with the rest of `tests/` in one pytest invocation.
