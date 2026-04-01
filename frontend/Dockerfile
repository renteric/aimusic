# ─────────────────────────────────────────────────────────────────────────────
# AI-Powered-Music — Frontend Image (multi-stage)
#
# Stage 1: Build the Vue.js SPA with Vite
# Stage 2: Serve the built assets with nginx
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies first for better layer caching.
# Use npm install (generates lockfile if absent); switch to npm ci once
# package-lock.json is committed to the repository.
COPY package*.json ./
RUN npm install --prefer-offline

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
