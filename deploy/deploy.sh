#!/usr/bin/env bash
# Update the server's application from the git remote and restart the service.
# Run as the application user (megaempires), not as root.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/megaempires/mega-empires-backend}"
VENV_DIR="${VENV_DIR:-/home/megaempires/venv}"
SERVICE="${SERVICE:-mega-empires-backend.service}"
BRANCH="${BRANCH:-main}"
SYSTEMCTL="/usr/bin/systemctl"

INSTALLED_UNIT="/etc/systemd/system/$SERVICE"

check_unit_drift() {
    # The deploy cannot install the unit file: the application account's sudo
    # right is limited to restarting alone. A change would therefore sit in the
    # repo without taking effect, and nothing would say so — the same silent
    # failure as the old skip-worktree arrangement.
    local repo_unit="$APP_DIR/deploy/mega-empires-backend.service"
    [ -f "$repo_unit" ] && [ -r "$INSTALLED_UNIT" ] || return 0
    if cmp -s "$repo_unit" "$INSTALLED_UNIT"; then
        return 0
    fi
    echo
    echo "======================================================================"
    echo " NOTE: the repo's unit file differs from the installed one."
    echo " The service restarted with the OLD unit. Run as an admin account:"
    echo
    echo "   sudo cp $repo_unit \\"
    echo "           $INSTALLED_UNIT"
    echo "   sudo systemctl daemon-reload"
    echo "   sudo systemctl restart $SERVICE"
    echo "======================================================================"
    echo
}

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
else
    echo "${previous_revision:0:8} -> ${current_revision:0:8}"
fi

# Dependencies are installed only when requirements.txt has changed.
if [ -f requirements.txt ] && ! git diff --quiet \
        "$previous_revision" "$current_revision" -- requirements.txt; then
    echo "== Installing dependencies =="
    "$VENV_DIR/bin/pip" install --upgrade -r requirements.txt
fi

# The test gate: tests/test_ui.py skips itself because the server has no
# tkinter. The rest run, and a failure prevents the restart.
echo "== Tests =="
if ! "$VENV_DIR/bin/python" -m unittest discover -q; then
    echo "ERROR: tests failed, the service will not be restarted." >&2
    exit 1
fi

echo "== Restarting $SERVICE =="
sudo "$SYSTEMCTL" restart "$SERVICE"
sleep 2

if "$SYSTEMCTL" is-active --quiet "$SERVICE"; then
    echo "OK: the service is running at revision ${current_revision:0:8}."
    check_unit_drift
else
    echo "ERROR: the service did not start." >&2
    echo "Check the log: journalctl -u $SERVICE -n 50 --no-pager" >&2
    exit 1
fi
