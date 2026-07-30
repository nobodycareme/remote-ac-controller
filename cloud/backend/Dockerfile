# Multi-stage build: frontend (Vite) + backend (tsc) -> slim runtime.
FROM node:24-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM node:24-slim AS backend-builder
WORKDIR /app/backend
COPY backend/package.json ./
RUN npm install --no-audit --no-fund
COPY backend/ ./
RUN npm run build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production
ENV NODE_OPTIONS=--max-old-space-size=192
COPY --from=backend-builder /app/backend /app
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 3100
CMD ["node", "dist/index.js"]
