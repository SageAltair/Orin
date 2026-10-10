FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/worker/pyproject.toml ./pyproject.toml
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --timeout 1200 --retries 10 "setuptools==75.8.0"
COPY apps/worker/src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --no-build-isolation --timeout 1200 --retries 10 .
CMD ["orin-worker"]
