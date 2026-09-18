#!/usr/bin/env bash
set -euo pipefail

IMAGE="atlas-bot:ci"
docker build --pull -t "$IMAGE" .
docker run --rm --entrypoint python "$IMAGE" -m pytest -q
docker run --rm --entrypoint python "$IMAGE" -m compileall -q .
