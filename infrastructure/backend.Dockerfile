FROM node:22-alpine AS website
WORKDIR /workspace/frontend
RUN npm install --global pnpm@11.25.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
ENV VITE_API_BASE_URL=/api/v1 VITE_MAP_STYLE_URL=""
RUN pnpm build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /workspace
COPY requirements.lock ./
RUN pip install -r requirements.lock
COPY backend ./backend
COPY data-pipeline ./data-pipeline
COPY docs/reports/harmonization ./docs/reports/harmonization
COPY tests ./tests
COPY pyproject.toml ./
COPY scripts/check_release.py ./scripts/check_release.py
COPY --from=website /workspace/frontend/dist ./frontend/dist
RUN pip install --no-deps -e ./backend -e ./data-pipeline \
    && python scripts/check_release.py --write-metadata \
    && useradd --create-home --uid 10001 firescope
USER firescope
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
