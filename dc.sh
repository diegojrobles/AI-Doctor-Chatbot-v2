#!/usr/bin/env bash
#
# docker compose wrapper for the EC2 host.
#
# docker-compose.yml requires POSTGRES_PASSWORD, which deploy.sh exports into
# its own process and nowhere else. That makes plain `docker compose ps` or
# `docker compose logs` fail with:
#
#     required variable POSTGRES_PASSWORD is missing a value
#
# This wrapper loads the same configuration deploy.sh does, then passes every
# argument through. Use it anywhere you would have used `docker compose`:
#
#     ./dc.sh ps
#     ./dc.sh logs -f api
#     ./dc.sh restart api
#     ./dc.sh down

set -euo pipefail

if [[ ! -f deploy.env ]]; then
    echo "ERROR: deploy.env not found. Run this from the repository root." >&2
    exit 1
fi

# shellcheck disable=SC1091
set -a; source deploy.env; set +a

SSM_PATH="${AIDOCTOR_SSM_PATH:-/aidoctor/prod/}"
export AIDOCTOR_SSM_PATH="$SSM_PATH"

POSTGRES_PASSWORD="$(aws ssm get-parameter \
    --name "${SSM_PATH}POSTGRES_PASSWORD" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text)"
export POSTGRES_PASSWORD

exec docker compose "$@"
