#!/usr/bin/env bash
# Update the server's application from the git remote and rebuild the container.
# Run as the application user (megaempires), not as root.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/megaempires/mega-empires-manager}"
BRANCH="${BRANCH:-main}"
IMAGE="${IMAGE:-mega-empires-manager-app}"

cd "$APP_DIR"

# The server should have no local changes: they would disappear unnoticed.
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: the working tree has uncommitted changes." >&2
    git status --short >&2
    exit 1
fi

echo "== Fetching origin/$BRANCH =="
git fetch --prune origin
previous_revision="$(git rev-parse HEAD)"
git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"
current_revision="$(git rev-parse HEAD)"

if [ "$previous_revision" = "$current_revision" ]; then
    echo "No new commits (${current_revision:0:8})."
fi
echo "${previous_revision:0:8} -> ${current_revision:0:8}"

# Snapshot whatever is currently running, before the build can overwrite :latest.
if docker image inspect "$IMAGE:latest" >/dev/null 2>&1; then
    docker tag "$IMAGE:latest" "$IMAGE:prev"
fi

# The test gate lives in the build (see Dockerfile). A failure here means the
# image never finishes, docker compose up is never reached, and the currently
# running container is untouched.
echo "== Building (tests run inside) =="
if ! docker compose build; then
    echo "ERROR: build/tests failed, the running container was not touched." >&2
    exit 1
fi

echo "== Recreating containers =="
docker compose up -d

sleep 2
if docker compose ps --status running --services | grep -q '^app$'; then
    echo "OK: running at revision ${current_revision:0:8}."
else
    echo "ERROR: app container did not come up." >&2
    echo "Check: docker compose logs app --tail 50" >&2
    exit 1
fi