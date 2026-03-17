#!/usr/bin/env bash
set -euo pipefail

HOST="dev"
PROJECT_DIR="${PROJECT_DIR:-/opt/dev.medica.im/backend}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-development.yml}"
GIT_BRANCH="${GIT_BRANCH:-dev}"

SECONDS=0

ssh "$HOST" bash -s <<EOF
set -euo pipefail
cd "$PROJECT_DIR"

echo "==> Pulling repo ($GIT_BRANCH)..."
git pull origin "$GIT_BRANCH"

echo "==> Building and restarting..."
docker compose -f "$COMPOSE_FILE" up --build -d
EOF

duration=$SECONDS
echo "==> Backend deployed in $((duration / 60))m $((duration % 60))s"
