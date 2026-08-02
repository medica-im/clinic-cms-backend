#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<USAGE
Usage: $(basename "$0") [-h] [-v]

Deploy the backend to the staging server: pulls the latest code,
pulls the latest production image from GHCR, and restarts the
docker compose stack over SSH. Does not build the backend image.

The database image is only rebuilt when the postgres:14 base image
has actually been updated upstream, so unchanged deploys leave every
container running untouched.

Options:
  -h, --help       Show this help message and exit
  -v, --verbose    Show full image pull progress

Environment variables:
  PROJECT_DIR   Remote project directory (default: /opt/dev.medica.im/backend)
  COMPOSE_FILE  Compose file to use (default: docker-compose-production.yml)
  GIT_BRANCH    Branch to pull (default: production)
USAGE
}

VERBOSE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

HOST="staging"
PROJECT_DIR="${PROJECT_DIR:-/opt/dev.medica.im/backend}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-production.yml}"
GIT_BRANCH="${GIT_BRANCH:-production}"

SECONDS=0

PULL_QUIET_FLAG="--quiet"
if [[ "$VERBOSE" -eq 1 ]]; then
    PULL_QUIET_FLAG=""
fi

ssh "$HOST" bash -s <<EOF
set -euo pipefail
cd "$PROJECT_DIR"

echo "==> Pulling repo ($GIT_BRANCH)..."
git pull origin "$GIT_BRANCH"

echo "==> Pulling latest image..."
docker compose -f "$COMPOSE_FILE" pull --ignore-buildable $PULL_QUIET_FLAG

echo "==> Checking postgres:14 base image..."
base_digest=\$(docker buildx imagetools inspect postgres:14 --format '{{.Manifest.Digest}}' 2>/dev/null || true)
built_digest=\$(docker image inspect postgres-non-root --format '{{index .Config.Labels "base.digest"}}' 2>/dev/null || true)

if [[ -z "\$base_digest" ]]; then
    echo "    could not query registry, skipping database rebuild"
elif [[ "\$base_digest" == "\$built_digest" ]]; then
    echo "    up to date (\${base_digest:0:19}), skipping rebuild"
else
    if [[ -z "\$built_digest" ]]; then
        echo "    no recorded base digest, rebuilding"
    else
        echo "    update available: \${built_digest:0:19} -> \${base_digest:0:19}"
    fi
    POSTGRES_BASE_DIGEST="\$base_digest" \\
        docker compose -f "$COMPOSE_FILE" build --pull database
fi

echo "==> Restarting..."
docker compose -f "$COMPOSE_FILE" up -d
EOF

duration=$SECONDS
echo "==> Backend deployed in $((duration / 60))m $((duration % 60))s"
