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
