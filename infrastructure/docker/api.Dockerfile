FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/src ./src
COPY apps/api/migrations ./migrations
COPY apps/api/tests ./tests
COPY apps/api/alembic.ini ./alembic.ini
RUN pip install --no-cache-dir --timeout 600 --retries 10 ".[dev]"
EXPOSE 8000
CMD ["uvicorn", "orin_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
