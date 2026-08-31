#!/usr/bin/env bash
#
# Deploy / redeploy the AI Doctor backend on the EC2 host.
#
# Run this ON the server, from the repository root:
#
#     ./deploy.sh
#
# What it does:
#   1. reads the database password from SSM Parameter Store into the shell
#      (never to a file on disk)
#   2. reads non-secret config from deploy.env
#   3. rebuilds and restarts the compose stack
#   4. waits for the app to report healthy
#
# Application secrets (OPENROUTER_API_KEY, PINECONE_API_KEY) are NOT handled
# here. The api container fetches those itself at start via backend/entrypoint.py
# using the instance's IAM role. See DEPLOYMENT.md.

set -euo pipefail

SSM_PATH="${AIDOCTOR_SSM_PATH:-/aidoctor/prod/}"
CONFIG_FILE="deploy.env"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: $CONFIG_FILE not found. Copy deploy.env.example and fill it in." >&2
    exit 1
fi

# Non-secret configuration: DOMAIN, ACME_EMAIL, ALLOWED_ORIGINS, AWS_REGION, MODEL.
# shellcheck disable=SC1090
set -a; source "$CONFIG_FILE"; set +a

: "${DOMAIN:?DOMAIN must be set in $CONFIG_FILE}"
: "${ACME_EMAIL:?ACME_EMAIL must be set in $CONFIG_FILE}"
: "${ALLOWED_ORIGINS:?ALLOWED_ORIGINS must be set in $CONFIG_FILE}"

if [[ "$ALLOWED_ORIGINS" == *"*"* ]]; then
    echo "ERROR: ALLOWED_ORIGINS must not contain '*' in production." >&2
    exit 1
fi

echo "==> Reading database password from SSM (${SSM_PATH}POSTGRES_PASSWORD)"
POSTGRES_PASSWORD="$(aws ssm get-parameter \
    --name "${SSM_PATH}POSTGRES_PASSWORD" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text)"
export POSTGRES_PASSWORD
export AIDOCTOR_SSM_PATH="$SSM_PATH"

if [[ -z "$POSTGRES_PASSWORD" || "$POSTGRES_PASSWORD" == "None" ]]; then
    echo "ERROR: could not read POSTGRES_PASSWORD from SSM." >&2
    exit 1
fi

echo "==> Building and starting the stack"
docker compose up -d --build

echo "==> Waiting for the application to become healthy"
for attempt in $(seq 1 40); do
    if docker compose exec -T api curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        echo "==> Application is healthy"
        echo
        echo "Verify from outside AWS:"
        echo "    curl https://${DOMAIN}/health"
        exit 0
    fi
    sleep 5
done

echo "ERROR: the application did not become healthy in time. Recent logs:" >&2
docker compose logs --tail 50 api >&2
exit 1
