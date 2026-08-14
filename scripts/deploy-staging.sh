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
container running untouched. If the database container does get
recreated, the app services are restarted so they drop the database
connections that recreation invalidated.

Options:
  -h, --help       Show this help message and exit
  -v, --verbose    Show full image pull progress

Environment variables:
  HOST          SSH destination: an alias from ~/.ssh/config, or user@address
                (default: staging). Whichever machine runs this script needs
                the alias defined and a key that reaches it.
  PROJECT_DIR   Remote project directory (default: /opt/backend)
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

HOST="${HOST:-staging}"
# /opt/backend since the August 2026 move to a new staging server. The old path
# was /opt/dev.medica.im/backend, named after a host that had not been called
# dev.medica.im for years; the new server puts each deploy directory at
# /opt/<what it is>.
PROJECT_DIR="${PROJECT_DIR:-/opt/backend}"
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

# Only where the deploy directory is still a checkout. The new staging server
# holds just the compose file and the .env — nothing there is built from
# source, so there is no repository to pull and this would abort the deploy on
# a server that is working exactly as intended.
if [[ -d .git ]]; then
    echo "==> Pulling repo ($GIT_BRANCH)..."
    git pull origin "$GIT_BRANCH"
else
    echo "==> No checkout here; compose file is managed by infra/"
fi

echo "==> Pulling latest image..."
docker compose -f "$COMPOSE_FILE" pull --ignore-buildable $PULL_QUIET_FLAG

# The database image is pulled with everything else now, not built here. It
# still records the postgres:14 digest it was built from, so this reports when
# upstream has moved — but rebuilding is a job for
# infra/scripts/build-postgres-image.sh on a workstation, not for a server that
# no longer has the repository to build from.
echo "==> Checking postgres:14 base image..."
base_digest=\$(docker buildx imagetools inspect postgres:14 --format '{{.Manifest.Digest}}' 2>/dev/null || true)
built_digest=\$(docker image inspect ghcr.io/medica-im/postgres-non-root:14 --format '{{index .Config.Labels "base.digest"}}' 2>/dev/null || true)
built_digest="\${built_digest##*@}"

if [[ -z "\$base_digest" || -z "\$built_digest" ]]; then
    echo "    could not compare digests, skipping the check"
elif [[ "\$base_digest" == "\$built_digest" ]]; then
    echo "    up to date (\${base_digest:0:19})"
else
    echo "    update available: \${built_digest:0:19} -> \${base_digest:0:19}"
    echo "    rebuild with: infra/scripts/build-postgres-image.sh"
fi

echo "==> Restarting..."
docker compose -f "$COMPOSE_FILE" up -d

# A restarted database drops every open connection, and the app services keep
# reusing the dead pooled ones ("the connection is closed"). depends_on only
# orders startup, so restart any app service older than the database itself.
# Comparing start times catches this whoever caused it, not just this run.
db_started=\$(docker inspect backend-database-1 --format '{{.State.StartedAt}}' 2>/dev/null || true)
stale=""

for svc in django fastapi celery; do
    svc_started=\$(docker inspect "backend-\${svc}-1" --format '{{.State.StartedAt}}' 2>/dev/null || true)
    if [[ -n "\$db_started" && -n "\$svc_started" && "\$svc_started" < "\$db_started" ]]; then
        stale="\$stale \$svc"
    fi
done

if [[ -n "\$stale" ]]; then
    echo "==> Database is newer, restarting stale services:\$stale"
    docker compose -f "$COMPOSE_FILE" restart \$stale
fi
EOF

duration=$SECONDS
echo "==> Backend deployed in $((duration / 60))m $((duration % 60))s"
