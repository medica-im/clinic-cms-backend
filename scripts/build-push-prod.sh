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
