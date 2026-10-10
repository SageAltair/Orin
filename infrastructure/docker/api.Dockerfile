FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/pyproject.toml ./pyproject.toml
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --timeout 1200 --retries 10 "setuptools==75.8.0"
COPY apps/api/src ./src
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./alembic.ini
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --no-build-isolation --timeout 1200 --retries 10 .
EXPOSE 8000
CMD ["uvicorn", "orin_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
