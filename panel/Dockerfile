# 1) build deps
FROM node:20-bullseye-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# 2) build app
FROM node:20-bullseye-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NODE_ENV=production
RUN npm run build

# 3) runtime image
FROM node:20-bullseye-slim
WORKDIR /app
ENV NODE_ENV=production
# next export
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./public
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
