# Yield Guardian API: FastAPI, the models and the investigator.
#
# Build from the repository root:
#   docker build -f deploy/docker/api.Dockerfile -t yield-guardian-api .
#
# The same image serves the API (default command) and runs database migrations as a one-shot
# command (`yg-migrate`, which runs `alembic upgrade head`; see deploy/compose/compose.yaml).
# Admin password hash: docker compose run --rm -it api python scripts/hash_password.py
# Model bundles are downloaded and verified at build time from deploy/artifacts.lock.json.

ARG PYTHON_IMAGE=python:3.13-slim-trixie

# ---------------------------------------------------------------------------------------------
# Dependencies and the API package, installed with uv from the lock file into /app/.venv.
FROM ${PYTHON_IMAGE} AS build

ARG UV_VERSION=0.11.32
RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore \
      "uv==${UV_VERSION}"

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# The repository layout is kept (/app/services/api): yield_guardian.db.migrate finds alembic.ini
# and alembic/ next to src/, both for `yg-migrate` and for migrations at API startup.
WORKDIR /app/services/api

# Third-party dependencies first, so source changes do not reinstall them.
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY services/api/README.md ./
COPY services/api/src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev \
 && python3 -m compileall -q src

# ---------------------------------------------------------------------------------------------
# Model bundles: downloaded, checked against the lock and every MANIFEST.json, or the build fails.
FROM ${PYTHON_IMAGE} AS artifacts

COPY deploy/fetch_artifacts.py deploy/artifacts.lock.json /fetch/
# Bundles committed to the repository (artifacts/<name>/<version>/) are verified file by file.
COPY artifacts/ /artifacts/
RUN python3 /fetch/fetch_artifacts.py --verify-local /artifacts \
 && python3 /fetch/fetch_artifacts.py --lock /fetch/artifacts.lock.json --dest /artifacts

# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# libgomp1: OpenMP runtime that LightGBM needs. Nothing else is added to the base image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 yieldguardian \
 && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home \
      --shell /usr/sbin/nologin yieldguardian

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    ARTIFACTS_DIR=/app/artifacts \
    SECOM_DATA_DIR=/app/data/secom

WORKDIR /app/services/api

COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/services/api/ /app/services/api/
# Database migrations and the admin password hasher.
COPY services/api/alembic.ini /app/services/api/
COPY services/api/alembic/ /app/services/api/alembic/
COPY services/api/scripts/ /app/services/api/scripts/
# SECOM, redistributed unmodified under CC BY 4.0; ATTRIBUTION.md travels with the data.
COPY data/secom/ATTRIBUTION.md data/secom/secom.data data/secom/secom_labels.data \
     data/secom/secom.names /app/data/secom/
# Dataset provenance (sources, licences, file hashes) for the methods page.
COPY data/manifest.json /app/data/manifest.json
COPY --from=artifacts /artifacts/ /app/artifacts/
# Curated literature for the knowledge search (agent/wiring.py reads /app/docs/knowledge).
COPY docs/knowledge/ /app/docs/knowledge/
# Recorded demo investigations (imported at startup when investigations.json exists).
COPY docs/recorded/ /app/docs/recorded/
COPY --chmod=0755 deploy/docker/api-migrate.sh /usr/local/bin/yg-migrate

ARG GIT_COMMIT=""
LABEL org.opencontainers.image.title="Yield Guardian API" \
      org.opencontainers.image.source="https://github.com/anas-aldahamsheh/yield-guardian" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${GIT_COMMIT}"
ENV GIT_COMMIT=${GIT_COMMIT}

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

CMD ["uvicorn", "yield_guardian.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
