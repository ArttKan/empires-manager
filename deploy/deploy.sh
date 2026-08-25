#!/usr/bin/env bash
# Päivitä palvelimen sovellus git-remotesta ja käynnistä palvelu uudelleen.
# Ajetaan sovelluskäyttäjänä (megaempires), ei rootina.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/megaempires/mega-empires-backend}"
VENV_DIR="${VENV_DIR:-/home/megaempires/venv}"
SERVICE="${SERVICE:-mega-empires-backend.service}"
BRANCH="${BRANCH:-master}"
SYSTEMCTL="/usr/bin/systemctl"

INSTALLED_UNIT="/etc/systemd/system/$SERVICE"

check_unit_drift() {
    # Deploy ei voi asentaa unit-tiedostoa: sovelluskäyttäjän sudo-oikeus on
    # rajattu pelkkään uudelleenkäynnistykseen. Muutos jäisi siis repoon ilman
    # että se tulee voimaan, eikä mikään kertoisi siitä — sama hiljainen
    # epäonnistuminen kuin aiemmalla skip-worktree-viritelmällä.
    local repo_unit="$APP_DIR/deploy/mega-empires-backend.service"
    [ -f "$repo_unit" ] && [ -r "$INSTALLED_UNIT" ] || return 0
    if cmp -s "$repo_unit" "$INSTALLED_UNIT"; then
        return 0
    fi
    echo
    echo "======================================================================"
    echo " HUOM: repon unit-tiedosto eroaa käytössä olevasta."
    echo " Palvelu käynnistyi VANHALLA unitilla. Aja admin-tunnuksella:"
    echo
    echo "   sudo cp $repo_unit \\"
    echo "           $INSTALLED_UNIT"
    echo "   sudo systemctl daemon-reload"
    echo "   sudo systemctl restart $SERVICE"
    echo "======================================================================"
    echo
}

cd "$APP_DIR"

# Palvelimella ei pidä olla paikallisia muutoksia: ne katoaisivat huomaamatta.
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "VIRHE: työhakemistossa on committoimattomia muutoksia." >&2
    git status --short >&2
    exit 1
fi

echo "== Haetaan origin/$BRANCH =="
git fetch --prune origin
previous_revision="$(git rev-parse HEAD)"
git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"
current_revision="$(git rev-parse HEAD)"

if [ "$previous_revision" = "$current_revision" ]; then
    echo "Ei uusia commiteja (${current_revision:0:8})."
else
    echo "${previous_revision:0:8} -> ${current_revision:0:8}"
fi

# Riippuvuudet asennetaan vain jos requirements.txt on muuttunut.
if [ -f requirements.txt ] && ! git diff --quiet \
        "$previous_revision" "$current_revision" -- requirements.txt; then
    echo "== Asennetaan riippuvuudet =="
    "$VENV_DIR/bin/pip" install --upgrade -r requirements.txt
fi

# Testiportti: tests/test_ui.py ohittaa itsensä, koska palvelimella ei ole
# tkinteriä. Muut testit ajetaan ja epäonnistuminen estää uudelleenkäynnistyksen.
echo "== Testit =="
if ! "$VENV_DIR/bin/python" -m unittest discover -q; then
    echo "VIRHE: testit epäonnistuivat, palvelua ei käynnistetä uudelleen." >&2
    exit 1
fi

echo "== Käynnistetään $SERVICE uudelleen =="
sudo "$SYSTEMCTL" restart "$SERVICE"
sleep 2

if "$SYSTEMCTL" is-active --quiet "$SERVICE"; then
    echo "OK: palvelu on käynnissä revisiossa ${current_revision:0:8}."
    check_unit_drift
else
    echo "VIRHE: palvelu ei käynnistynyt." >&2
    echo "Katso loki: journalctl -u $SERVICE -n 50 --no-pager" >&2
    exit 1
fi
