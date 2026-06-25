# ── Stage 1: Build frontend ────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY src/package.json src/package-lock.json* ./
RUN npm ci
COPY src/ .
RUN npm run build

# ── Stage 2: Backend + serve frontend static files ─────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY scripts/ ./scripts/

# Copy frontend build into static directory served by FastAPI
COPY --from=frontend-builder /frontend/dist ./static/

EXPOSE 8000

# Run server (tables are created on startup via create_all)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
