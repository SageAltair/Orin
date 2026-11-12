FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Refresh the Debian security package before installing application dependencies.
# Trivy identified fixed zlib1g vulnerabilities in the base image (2026-11-07).
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/requirements.lock ./requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --timeout 1200 --retries 10 "setuptools==75.8.0"
COPY apps/api/src ./src
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./alembic.ini
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --timeout 120 --retries 3 -r requirements.lock \
    && pip install --no-deps --no-build-isolation . \
    && pip uninstall -y setuptools
RUN useradd --create-home --uid 10001 orin && mkdir -p /app/data/attachments /state && chown -R orin:orin /app /state
USER orin
EXPOSE 8000
CMD ["uvicorn", "orin_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
