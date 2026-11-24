#!/usr/bin/env bash
#
# Compile requirements/*.in into the pinned requirements/*.txt the image
# installs (docker/backend/Dockerfile), with pip-compile, inside the image's
# own Python so the pins fit it. See requirements/README.md.
#
# Usage:
#   scripts/compile-requirements.sh        keep the pins already in the .txt files,
#                                          resolve only what the .in files added
#   scripts/compile-requirements.sh -U     move every package to its latest version
#                                          the .in bounds allow
set -euo pipefail

PYTHON_IMAGE="${PYTHON_IMAGE:-python:3.14-slim-trixie}"

usage() { sed -n '2,/^set /p' "$0" | sed '$d; s/^# \{0,1\}//'; }

UPGRADE=""
for arg in "$@"; do
    case "$arg" in
        -U|--upgrade) UPGRADE="--upgrade" ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown option $arg" >&2; usage >&2; exit 2 ;;
    esac
done

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Each file is resolved against the ones before it (-c in the .in files), so
# the image's successive pip installs never disagree on a version.
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e PATH="/tmp/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    -v "$PWD:/work" -w /work "$PYTHON_IMAGE" bash -euc '
        pip install --user --quiet --no-warn-script-location pip-tools
        for name in common fastapi development test; do
            pip-compile --quiet --strip-extras '"$UPGRADE"' requirements/$name.in
        done
    '
git status --short requirements
