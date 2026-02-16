# Social Performance Coach API

## Database setup

This API supports two schema bootstrap paths:

1. Runtime bootstrap (default for local dev):
   - Set `AUTO_CREATE_DB_SCHEMA=true` in `.env`
   - The app will run `Base.metadata.create_all()` at startup.

2. Alembic migrations (recommended for controlled environments):
   - `cd apps/api`
   - `DATABASE_URL=postgresql://... ./venv/bin/alembic -c alembic.ini upgrade head`

Migration files live in `apps/api/alembic/versions`.

## Worker queue

Audit execution is queue-backed using Redis/RQ.

Start worker locally:

```bash
cd apps/api
python worker.py
```

## Security defaults

Startup now fails if insecure default secrets are still configured.
Set strong values for:
- `JWT_SECRET` (>=24 chars)
- `ENCRYPTION_KEY` (>=32 chars)
