#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/medica-im/clinic-cms-backend}"
DOCKERFILE="${DOCKERFILE:-docker/backend/Dockerfile}"
TARGET="${TARGET:-prod}"

cd "$(git rev-parse --show-toplevel)"

TAG="$(git rev-parse --short HEAD)"

echo "==> Building $IMAGE:$TAG (target=$TARGET)..."
docker build -f "$DOCKERFILE" --target "$TARGET" \
  -t "$IMAGE:latest" \
  -t "$IMAGE:$TAG" \
  .

echo "==> Pushing $IMAGE:latest and $IMAGE:$TAG..."
docker push "$IMAGE:latest"
docker push "$IMAGE:$TAG"

echo "==> Done: pushed $IMAGE:latest and $IMAGE:$TAG"

# --- The other image this backend needs --------------------------------------
# The database runs ghcr.io/medica-im/postgres-non-root:14, built from
# docker/postgres/Dockerfile in this repository but published separately, by
# infra/scripts/build-postgres-image.sh. Two images, one repository, and only
# one of them gets rebuilt when you run this.
#
# That asymmetry is the whole reason for this block. This script runs often;
# the postgres one runs when somebody remembers, which in practice means when
# something has already gone wrong. A published tag does not move on its own,
# so a change to docker/postgres/Dockerfile can sit unpublished indefinitely
# with nothing to say so.
#
# Reported, never run: rebuilding postgres as a side effect of building the
# backend would republish, unasked, the image every server pulls for its
# database. The check is cheap and the decision stays yours.
#
# Not fatal either. The backend image is built and pushed by this point, and
# failing here would imply otherwise.
# Anchored to this script's own location, not the working directory: infra is
# a sibling of this repository, and resolving "../infra" against wherever the
# caller happened to be would find it only by luck.
_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POSTGRES_CHECK="${POSTGRES_CHECK:-$_repo_root/../infra/scripts/build-postgres-image.sh}"
if [[ -x "$POSTGRES_CHECK" ]]; then
    echo
    if ! "$POSTGRES_CHECK" --check; then
        echo
        echo "    ^ the postgres image is stale. It is not part of this build;"
        echo "      rebuild it with:  $POSTGRES_CHECK   (without --check)"
    fi
else
    echo
    echo "note: could not find build-postgres-image.sh to check the database"
    echo "      image (looked at $POSTGRES_CHECK). Set POSTGRES_CHECK to point"
    echo "      at it, or check by hand from the infra repository."
fi
