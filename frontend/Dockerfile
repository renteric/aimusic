# ─────────────────────────────────────────────────────────────────────────────
# AI-Music — Frontend Image (multi-stage)
#
# Stage 1: Build the Vue.js SPA with Vite
# Stage 2: Serve the built assets with nginx
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies using the committed lockfile for a deterministic,
# reproducible install.  The BuildKit cache mount persists the npm cache
# across rebuilds so packages are not re-downloaded on every build.
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline \
        --fetch-retries=5 \
        --fetch-retry-mintimeout=10000 \
        --fetch-retry-maxtimeout=60000

# Copy source and build.
COPY . .
RUN npm run build

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Copy the built SPA into nginx's document root.
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace the default nginx config with our production config.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
