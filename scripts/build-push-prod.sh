#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/medica-im/clinic-cms-backend}"
DOCKERFILE="${DOCKERFILE:-docker/backend/Dockerfile}"
TARGET="${TARGET:-prod}"

cd "$(git rev-parse --show-toplevel)"

# Named after the last commit that changed what the image is built from
# (scripts/image-inputs), not HEAD: a commit to a script alone builds the same
# image, under the same name. The label says it too, so the commit can still
# be read from a running image once no local tag is left (skcms versions.sh).
mapfile -t INPUTS < <(grep -Ev '^[[:space:]]*(#|$)' scripts/image-inputs)
CODE_SHA="$(git rev-list -1 HEAD -- "${INPUTS[@]}")"
TAG="${CODE_SHA:0:7}"
if [[ -n "$(git status --porcelain -- "${INPUTS[@]}")" ]]; then
  echo "==> WARNING: building with uncommitted changes to the image's files:" >&2
  git status --short -- "${INPUTS[@]}" >&2
  echo "    $IMAGE:$TAG names a commit that does not contain what is in this image." >&2
fi

echo "==> Building $IMAGE:$TAG (target=$TARGET)..."
# --pull: a fresh base image brings current ca-certificates and pip, and
# invalidates the pip layer so certifi is re-resolved, so a revoked CA cannot
# survive in a cached image. certifi is transitive (via requests), not pinned.
# APT_REFRESH: the first build of each day reruns apt-get upgrade, which --pull
# alone does not when the base image is unchanged.
docker build --pull -f "$DOCKERFILE" --target "$TARGET" \
  --build-arg APT_REFRESH="$(date -u +%F)" \
  --label "git.sha=$CODE_SHA" \
  -t "$IMAGE:latest" \
  -t "$IMAGE:$TAG" \
  .

echo "==> Pushing $IMAGE:latest and $IMAGE:$TAG..."
docker push "$IMAGE:latest"
docker push "$IMAGE:$TAG"

echo "==> Done: pushed $IMAGE:latest and $IMAGE:$TAG"
