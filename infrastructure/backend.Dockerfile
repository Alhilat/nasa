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
RUN pip install --no-deps -e ./backend -e ./data-pipeline \
    && useradd --create-home --uid 10001 firescope
USER firescope
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
