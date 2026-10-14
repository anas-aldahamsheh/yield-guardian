# Yield Guardian web app: Next.js standalone server.
#
# Build from the repository root:
#   docker build -f deploy/docker/web.Dockerfile -t yield-guardian-web .
#
# Needs apps/web/next.config.ts to set `output: "standalone"` and `outputFileTracingRoot` to the
# repository root. The build never reaches the API; the server reads API_INTERNAL_URL and
# API_PUBLIC_URL at run time, so one image runs on any host.

ARG NODE_IMAGE=node:22-trixie-slim

# ---------------------------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS build

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1 \
    CI=1

WORKDIR /repo

# pnpm at the exact version of the root `packageManager` field.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable && corepack install

# Every package in the lock file goes to the store first, so source edits keep this layer.
RUN pnpm fetch

# Sources (.dockerignore keeps out mocks, tests, fixtures, caches and secrets).
COPY . .
RUN pnpm install --frozen-lockfile --offline

RUN NODE_ENV=production pnpm --filter @yield-guardian/web build \
 && test -f apps/web/.next/standalone/apps/web/server.js \
 && mkdir -p apps/web/public \
 && rm -f apps/web/public/mockServiceWorker.js

# ---------------------------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS runtime

# The runtime needs node only: package managers are removed.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
           /usr/local/bin/yarn /usr/local/bin/yarnpkg /opt/yarn-*

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app

COPY --from=build /repo/apps/web/.next/standalone/ ./
COPY --from=build /repo/apps/web/.next/static/ ./apps/web/.next/static/
COPY --from=build /repo/apps/web/public/ ./apps/web/public/
# The only folder the server writes to (image and fetch caches); a tmpfs in compose.
RUN mkdir -p apps/web/.next/cache && chown node:node apps/web/.next/cache

ARG GIT_COMMIT=""
LABEL org.opencontainers.image.title="Yield Guardian web" \
      org.opencontainers.image.source="https://github.com/anas-aldahamsheh/yield-guardian" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

USER node
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/healthz').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]

CMD ["node", "apps/web/server.js"]
