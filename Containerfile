FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/ backend/
COPY frontend/ frontend/
COPY demo/ demo/
COPY red-hat-examples/pizzeria-amalfi-bank-statement-2025-v6.csv red-hat-examples/
RUN chmod -R a+rX /app

USER 1001
EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
