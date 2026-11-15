# syntax=docker/dockerfile:1
# Build one Python service from the uv workspace: --build-arg PACKAGE=tsch-api|tsch-worker
FROM python:3.12.12-slim-bookworm AS build
ARG PACKAGE
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# Optional build secret `extra_ca`: only for builds behind a TLS-intercepting proxy.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir uv==0.11.32
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca UV_NATIVE_TLS=1; fi; \
    uv sync --frozen --no-dev --package "${PACKAGE}" --no-editable

FROM python:3.12.12-slim-bookworm
RUN groupadd --system --gid 10001 tsch && useradd --system --uid 10001 --gid 10001 --home /app tsch
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY services/api/alembic /app/alembic
COPY services/api/alembic.ini /app/alembic.ini
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER 10001:10001
