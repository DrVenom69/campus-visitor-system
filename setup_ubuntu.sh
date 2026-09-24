#!/usr/bin/env bash
# One-command setup for Ubuntu: installs PostgreSQL, creates the database, writes .env,
# creates the virtual environment, creates the tables and your admin account.
#
#   bash setup_ubuntu.sh
#
# Safe to run again: it never overwrites an existing .env.
set -euo pipefail
cd "$(dirname "$0")"

DB_NAME="campus_visitor"
DB_USER="visitor_admin"

as_postgres() {
    if [ "$(id -u)" -eq 0 ]; then su postgres -c "$*"; else sudo -u postgres bash -c "$*"; fi
}
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

echo "==> 1/6  Installing system packages (asks for your sudo password)"
$SUDO apt-get update -qq || echo "    (apt update reported a problem with some source; continuing)"
$SUDO apt-get install -y -qq python3 python3-venv python3-pip postgresql

echo "==> 2/6  Starting PostgreSQL"
$SUDO systemctl enable --now postgresql 2>/dev/null || $SUDO service postgresql start
for _ in 1 2 3 4 5 6 7 8 9 10; do
    as_postgres "pg_isready -q" && break
    sleep 1
done

if [ -f .env ] && grep -q '^DATABASE_URL=' .env; then
    echo "==> 3/6  .env already exists, keeping it"
else
    echo "==> 3/6  Creating the database and .env"
    DB_PASS="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
    SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

    if [ "$(as_postgres "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'\"")" = "1" ]; then
        as_postgres "psql -c \"ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';\"" >/dev/null
    else
        as_postgres "psql -c \"CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';\"" >/dev/null
    fi
    if [ "$(as_postgres "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\"")" != "1" ]; then
        as_postgres "psql -c \"CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};\"" >/dev/null
    fi

    umask 077
    cat > .env <<ENVFILE
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost/${DB_NAME}
APP_TIMEZONE=Asia/Dhaka
ENVFILE
    umask 022
fi

echo "==> 4/6  Creating the Python virtual environment"
[ -d venv ] || python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements-dev.txt

echo "==> 5/6  Creating the database tables"
TABLE_COUNT="$(as_postgres "psql -d ${DB_NAME} -tAc \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'\"" | tr -d '[:space:]')"
if [ "${TABLE_COUNT:-0}" != "0" ]; then
    echo "    The database already has ${TABLE_COUNT} table(s), possibly from an older version."
    ANSWER=""
    read -r -p "    Recreate them? This DELETES existing data. [y/N] " ANSWER || true
    if [[ "${ANSWER}" =~ ^[Yy]$ ]]; then
        flask --app run init-db --reset
    else
        flask --app run init-db
    fi
else
    flask --app run init-db
fi

echo "==> 6/6  Create your admin account"
flask --app run create-admin

DEMO=""
read -r -p "Add sample demo data so the pages are not empty? [y/N] " DEMO || true
if [[ "${DEMO}" =~ ^[Yy]$ ]]; then
    flask --app run seed-demo
fi

echo
echo "All set. To start the app:"
echo
echo "    cd $(pwd)"
echo "    source venv/bin/activate"
echo "    python run.py"
echo
echo "Then open http://127.0.0.1:5000 in your browser."
echo "Run the tests any time with:  pytest -q"
