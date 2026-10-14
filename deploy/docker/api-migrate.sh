#!/bin/sh
# One-shot database migration for the API image: `alembic upgrade head`.
# The compose service `migrate` runs it before the API starts; DATABASE_URL comes from the
# environment.
set -eu

cd /app/services/api
if [ ! -f alembic.ini ] || [ ! -d alembic ]; then
  echo "yg-migrate: /app/services/api/alembic.ini or alembic/ is missing from this image" >&2
  exit 1
fi
exec alembic -c /app/services/api/alembic.ini upgrade head
