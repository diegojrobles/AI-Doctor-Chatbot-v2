# syntax=docker/dockerfile:1
#
# AI Doctor backend. Build context is the repository root so that this file can
# be referenced as backend/Dockerfile from the root docker-compose.yml.
#
# Pinned to a specific Debian point release. Replace the tag with a @sha256:...
# digest once you have pulled it (see DEPLOYMENT.md, "Pinning the base image")
# if you want byte-for-byte reproducible builds.
#
# NO SECRETS ARE BAKED INTO THIS IMAGE. Configuration arrives at container start
# from SSM Parameter Store via entrypoint.py. See DEPLOYMENT.md.
FROM python:3.12-slim-bookworm

# - PYTHONDONTWRITEBYTECODE: no .pyc litter in the image or on the volume
# - PYTHONUNBUFFERED: logs reach `docker logs` immediately instead of being buffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libpq5 is the runtime library psycopg2-binary links against. curl is used by
# the compose healthcheck. Both are installed without recommends to keep the
# image small, and the apt lists are removed in the same layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies are copied and installed before the application code so that this
# layer stays cached when only application code changes.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/gunicorn.conf.py ./gunicorn.conf.py
COPY backend/entrypoint.py ./entrypoint.py

# Run as an unprivileged user. If the container is ever compromised, the
# attacker does not start as root inside it.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# entrypoint.py loads secrets from SSM (or passes through in local mode) and
# then exec's gunicorn, so gunicorn becomes PID 1 and receives stop signals.
ENTRYPOINT ["python", "entrypoint.py"]
CMD ["gunicorn", "--config", "gunicorn.conf.py"]
