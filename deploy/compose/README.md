# Yield Guardian on any Docker host

One compose file runs the whole product: PostgreSQL with pgvector, a one-shot migration, the API, the web app and a Caddy gateway. Only the gateway is published.

```
browser ──► gateway (Caddy) ──/api/*, /ws/*──► api:8000 ──► db:5432 (pgvector)
                            └─everything else─► web:3000 ──(server side)──► api:8000
```

## Requirements

Docker Engine 24 or later with the Compose plugin 2.24 or later, 4 GB of memory and about 5 GB of disk. Nothing else: images build from this repository.

## Start

From the repository root:

```sh
cp .env.example deploy/compose/.env
# Fill in the two required values:
#   POSTGRES_PASSWORD=$(openssl rand -hex 32)
#   SESSION_SECRET=$(openssl rand -base64 48)
docker compose -f deploy/compose/compose.yaml up -d --build --wait
```

Open http://localhost:8080 (or `http://<host>:<HTTP_PORT>`). `docker compose ... ps` shows every service healthy, and `migrate` as exited with code 0.

Stop with `docker compose -f deploy/compose/compose.yaml down`. Add `-v` to delete the database and the gateway's certificates as well.

## HTTPS with a domain

Point the domain's DNS at the host, open ports 80 and 443, and set in `deploy/compose/.env`:

```sh
DOMAIN=yield-guardian.example.com
HTTP_PORT=80
HTTPS_PORT=443
PUBLIC_URL=https://yield-guardian.example.com
```

Caddy then obtains and renews the certificate itself (stored in the `caddy-data` volume) and redirects HTTP to HTTPS. Without `DOMAIN`, the gateway serves plain HTTP on `HTTP_PORT`, which suits a laptop or a host behind another TLS-terminating proxy. In that case, list that proxy in `TRUSTED_PROXIES` so the forwarded client address and scheme are kept.

## Settings

Every setting comes from `deploy/compose/.env` and is documented in the repository's `.env.example`. The compose file adds the settings that follow from the stack itself:

| Service | Variable | Value |
|---|---|---|
| api, migrate | `DATABASE_URL` | `postgresql+asyncpg://yield_guardian:${POSTGRES_PASSWORD}@db:5432/yield_guardian` |
| api, migrate | `ENVIRONMENT` | `production` |
| api | `PUBLIC_URL` | `.env` value, else `http://localhost:${HTTP_PORT}` |
| api (image) | `ARTIFACTS_DIR`, `SECOM_DATA_DIR` | `/app/artifacts`, `/app/data/secom` |
| web | `API_INTERNAL_URL` | `http://api:8000` (server-side requests) |
| web | `API_PUBLIC_URL` | `/api/v1` (browsers use the gateway's origin; the live line is `/ws/line`) |
| gateway | `SITE_ADDRESS` | `DOMAIN`, else `:80` |

The API and the migration receive the whole `.env` file; the web app receives only the two URLs above. Leave optional settings commented out rather than empty, and quote values containing `$` with single quotes.

## Model bundles

The API image downloads the bundles listed in `deploy/artifacts.lock.json` while it builds, checks each archive's SHA-256 and every file in the bundle's `MANIFEST.json`, and fails the build on any mismatch (`deploy/fetch_artifacts.py`). With an empty lock the image has no bundles: `/api/v1/ready` reports them missing and model routes answer 503 `not_ready`. To publish a bundle, attach the archive to a GitHub Release and add its `name`, `version`, `url` and `sha256` to the lock.

## Security

- No secret is in an image or in the compose file. `.env` files are never committed and are excluded from the build context.
- All containers run with a read-only root filesystem (tmpfs for scratch paths), `no-new-privileges` and every Linux capability dropped. The gateway alone gets `NET_BIND_SERVICE` to bind ports 80 and 443.
- The API, the web app and the database run as non-root users.
- The database is on an internal network: it is reachable from the API and the migration only, and has no route to the internet.
- No request limits of any kind (decision D-009): the gateway does no rate limiting and caps no request size.

## Data licence

The API image contains the SECOM dataset (UCI Machine Learning Repository, CC BY 4.0) with its `ATTRIBUTION.md`, at `/app/data/secom/`.
