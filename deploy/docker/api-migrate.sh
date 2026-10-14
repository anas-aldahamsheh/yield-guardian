#!/bin/sh
# One-shot database migration for the API image: `alembic upgrade head`.
# The compose service `migrate` runs it before the API starts; DATABASE_URL comes from the
# environment.
set -eu

cd /app
if [ ! -f alembic.ini ]; then
  echo "yg-migrate: this image contains no database migrations (no alembic.ini); nothing to apply"
  exit 0
fi
exec alembic -c /app/alembic.ini upgrade head
