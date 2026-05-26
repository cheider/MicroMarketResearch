# Tests

**Standards:** [docs/TESTING_STANDARDS.md](../docs/TESTING_STANDARDS.md) — reversible runs, no damage to `analytics.db`, no Clover calls in `pytest`.

```powershell
pytest -v
```

Fixtures live in `conftest.py` (isolated temp SQLite per `app` fixture). Helpers in `test_helpers.py`.
