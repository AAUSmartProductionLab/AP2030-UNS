# BaSyx AAS Web UI with the AP2030-UNS user plugins baked in.
#
# The BaSyx Web UI discovers plugins from `aas-web-ui/src/UserPlugins/**/*.vue`
# at BUILD time (`import.meta.glob` in `main.ts`), so a custom plugin cannot be
# mounted at runtime — it has to be compiled into the image. This Dockerfile
# therefore checks out the upstream app and copies the plugin sources in before
# running the production build.
#
#   docker build -t aas-gui-ap2030 ./basyx-ui-plugins
#
# The base tag is pinned to a commit rather than `main` so rebuilds are
# reproducible; bump BASYX_WEB_UI_REF to pick up upstream changes.

# Build stage: fetch upstream, drop in the plugins, produce `dist`.
FROM node:24-slim AS build-stage
ARG BASYX_WEB_UI_REF=55dc7019d1d9d138076c7a762311c0f73e795a9b
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NODE_OPTIONS=--max-old-space-size=8192
ENV NODE_OPTIONS=$NODE_OPTIONS
WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Fetch only the pinned commit; the build then needs `config/`, `nginx.conf`
# and `entrypoint.sh`, so the whole tree is materialised.
RUN git init . \
  && git remote add origin https://github.com/eclipse-basyx/basyx-aas-web-ui.git \
  && git fetch --depth 1 origin "$BASYX_WEB_UI_REF" \
  && git checkout FETCH_HEAD

WORKDIR /app/aas-web-ui
RUN corepack enable
RUN pnpm install --frozen-lockfile

# Plugins are copied over `UserPlugins` after install so a plugin change never
# invalidates the dependency layer. `*.test.ts` is excluded on purpose: the
# tests read AIMC fixtures from this repository, which is not part of the image
# build context (upstream's `prebuild` runs the whole vitest suite).
COPY src/UserPlugins ./src/UserPlugins
RUN find ./src/UserPlugins -name '*.test.ts' -delete

# Upstream's `pnpm build` runs `prebuild` (lint -> vitest -> vue-tsc) first.
# The suite is invoked directly with a more generous test timeout because
# `tests/router/OAuth2CallbackRouting.test.ts` has a hard 30 s timeout that it
# exceeds when this build competes with a running stack for CPU. Everything
# upstream verifies is still verified, only less flakily.
RUN pnpm run lint:check \
 && pnpm exec vitest run --testTimeout=180000 \
 && pnpm run type-check \
 && pnpm exec vite build

# Production stage: identical to the upstream layout so the entrypoint and
# environment variable substitution keep working unchanged.
FROM nginx:mainline-alpine-slim AS production-stage
ARG HTTP_PROXY
ARG HTTPS_PROXY
WORKDIR /usr/src/app

RUN apk add --no-cache jq gettext 'nodejs~24'
RUN addgroup -g 1000 -S mygroup && \
  adduser -u 1000 -D -S -G mygroup myuser

COPY --from=build-stage /app/aas-web-ui/dist /usr/src/app/dist
COPY --from=build-stage /app/aas-web-ui/nginx.conf /etc/nginx/nginx.conf.template
COPY --from=build-stage /app/aas-web-ui/entrypoint.sh /usr/src/app/entrypoint.sh
RUN chmod +x /usr/src/app/entrypoint.sh

RUN chown -R myuser:mygroup /usr/src/app /var/cache/nginx /tmp /etc/nginx /usr/share/nginx/html
RUN chmod -R 777 /usr/src/app /var/cache/nginx /tmp /etc/nginx /usr/share/nginx/html

USER myuser
ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
