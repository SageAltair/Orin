FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/worker/pyproject.toml ./pyproject.toml
COPY apps/worker/requirements.lock ./requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --timeout 1200 --retries 10 "setuptools==75.8.0"
COPY apps/worker/src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check --timeout 120 --retries 3 -r requirements.lock && pip install --no-deps --no-build-isolation .
RUN useradd --create-home --uid 10001 orin && mkdir -p /app/data/attachments /state && chown -R orin:orin /app /state
USER orin
CMD ["orin-worker"]
