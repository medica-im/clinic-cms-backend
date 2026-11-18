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
#
# Production is two machines, not one. `production` runs the annuaire itself;
# `annuaire.medica.im` runs the sandbox against the same production image. Both
# want the same image at the same time, so deploying to one and remembering the
# other later is how they drift apart. Deploying both is the default.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING_SCRIPT="$HERE/deploy-staging.sh"

# Each target is "host:directory". HOST/PROJECT_DIR still override, and still
# name a single machine, so a one-off deploy to one of them needs no new script.
TARGETS=(
    # The annuaire.
    "production:/opt/backend"
    # The sandbox. Its /opt/annuaire.medica.im is the frontend, not this.
    "annuaire.medica.im:/opt/backend"
)
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-production.yml}"
GIT_BRANCH="${GIT_BRANCH:-production}"

# An explicit HOST means that machine and no other.
if [[ -n "${HOST:-}" ]]; then
    TARGETS=("$HOST:${PROJECT_DIR:-/opt/backend}")
fi

usage() {
    cat <<USAGE
Usage: $(basename "$0") [-h] [-v] [-y]

Deploy the backend to every production machine: the annuaire and the sandbox.
Pulls the latest code and image and restarts the stack over SSH, exactly as
deploy-staging.sh does — this only points it at production and asks first.

Options:
  -h, --help       Show this help message and exit
  -v, --verbose    Show full image pull progress
  -y, --yes        Do not ask for confirmation

Environment variables:
  HOST          Deploy to this one machine instead of all of them
  PROJECT_DIR   Remote project directory for that machine (default: /opt/backend)
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

  branch     $GIT_BRANCH
  compose    $COMPOSE_FILE

MSG
    for target in "${TARGETS[@]}"; do
        printf '  %s  %s\n' "${target%%:*}" "${target#*:}"
    done
    echo
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

# Not exec: that would replace this process and never reach the second target.
# Nor set -e alone — a failed first host would abort before the second is even
# attempted, leaving the two on different images with no word about it. Each
# host is tried, and the failures are reported together at the end.
failed=()
for target in "${TARGETS[@]}"; do
    host="${target%%:*}"
    echo
    echo "======> $host"
    if ! HOST="$host" \
         PROJECT_DIR="${target#*:}" \
         COMPOSE_FILE="$COMPOSE_FILE" \
         GIT_BRANCH="$GIT_BRANCH" \
         "$STAGING_SCRIPT" ${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"}; then
        echo "error: deploy to $host failed" >&2
        failed+=("$host")
    fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
    echo >&2
    echo "error: deploy failed on: ${failed[*]}" >&2
    exit 1
fi
