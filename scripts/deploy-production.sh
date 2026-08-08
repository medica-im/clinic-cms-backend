#!/usr/bin/env bash
#
# Deploy the backend to production.
#
# The deploy itself is deploy-staging.sh: the two differ only in which machine
# and directory they touch, and everything that makes that script careful — the
# postgres:14 digest check, restarting app services whose database was recreated
# under them — is worth exactly as much here. Copying it would leave two versions
# to keep in step, and the production copy would be the one that quietly fell
# behind.
#
# What this adds is the part that should differ: production values, and a pause
# to confirm them before anything is touched.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_SCRIPT="$HERE/deploy-staging.sh"

# Overridable like deploy-staging.sh's own defaults, so a second production
# machine needs no new script.
HOST="${HOST:-production}"
# Alongside the frontends, which live at /opt/annuaire.medica.im/<site>.
PROJECT_DIR="${PROJECT_DIR:-/opt/annuaire.medica.im/backend}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-production.yml}"
GIT_BRANCH="${GIT_BRANCH:-production}"

usage() {
    cat <<USAGE
Usage: $(basename "$0") [-h] [-v] [-y]

Deploy the backend to the production server. Pulls the latest code and image
and restarts the stack over SSH, exactly as deploy-staging.sh does — this only
points it at production and asks first.

Options:
  -h, --help       Show this help message and exit
  -v, --verbose    Show full image pull progress
  -y, --yes        Do not ask for confirmation

Environment variables:
  HOST          SSH destination (default: $HOST)
  PROJECT_DIR   Remote project directory (default: $PROJECT_DIR)
  COMPOSE_FILE  Compose file to use (default: $COMPOSE_FILE)
  GIT_BRANCH    Branch to pull (default: $GIT_BRANCH)
USAGE
}

ASSUME_YES=0
PASS_THROUGH=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        -v|--verbose) PASS_THROUGH+=("$1"); shift ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if [[ ! -x "$STAGING_SCRIPT" ]]; then
    echo "error: $STAGING_SCRIPT is missing or not executable" >&2
    exit 1
fi

if [[ $ASSUME_YES -eq 0 ]]; then
    cat <<MSG
About to deploy the backend to PRODUCTION:

  host       $HOST
  directory  $PROJECT_DIR
  branch     $GIT_BRANCH
  compose    $COMPOSE_FILE

MSG
    # From the terminal, not from the pipe a script might be feeding in: read
    # would otherwise take a line of that input as the answer.
    if [[ ! -t 0 ]]; then
        echo "error: no terminal to confirm on; pass --yes to deploy unattended." >&2
        exit 1
    fi
    read -r -p "Deploy to production? [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "Aborted."; exit 1 ;;
    esac
fi

HOST="$HOST" \
PROJECT_DIR="$PROJECT_DIR" \
COMPOSE_FILE="$COMPOSE_FILE" \
GIT_BRANCH="$GIT_BRANCH" \
    exec "$STAGING_SCRIPT" ${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"}
