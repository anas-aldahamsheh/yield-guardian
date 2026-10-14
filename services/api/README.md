# Yield Guardian API

FastAPI service that owns the data, the models, the investigator and the product rules. See `docs/PLAN.md` at the repository root.

## Database

PostgreSQL with pgvector. Migrations live in `alembic/` and run at API startup under an advisory lock (`build_persistence(..., migrate=True)`), or by hand from this directory:

```sh
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/yield_guardian uv run alembic upgrade head
```

Admin sign-in needs `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH`. Make the hash with `uv run python scripts/hash_password.py` (format `scrypt$<n>$<r>$<p>$<salt>$<hash>`, base64url without padding).

Database tests run when `TEST_DATABASE_URL` is set: each test session creates a temporary database next to it, migrates it and drops it at the end.
