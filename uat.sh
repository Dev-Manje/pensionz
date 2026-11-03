#!/usr/bin/env bash
# Pensionz UAT server helper (Linux, Docker Compose v2). See UAT.md.
#
#   ./uat.sh install   first time: .env from .env.uat.example, build, start, migrate, load the UAT data
#   ./uat.sh update    after `git pull`: rebuild, restart, migrate (keeps the data)
#   ./uat.sh seed      load the UAT data again (adds only what is missing)
#   ./uat.sh reset     WIPE the database and documents, then migrate and load fresh UAT data
#   ./uat.sh status    containers and URLs
#   ./uat.sh logs      follow the API and worker logs
#   ./uat.sh stop      stop everything (data kept)
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.uat.yml)

need_env() {
  if [ ! -f .env ]; then
    cp .env.uat.example .env
    echo "Created .env from .env.uat.example."
    echo "Edit it now: replace UAT_HOST with this server's address and change the passwords/secret,"
    echo "then run ./uat.sh install again."
    exit 1
  fi
  if grep -q "UAT_HOST" .env; then
    echo ".env still contains UAT_HOST — replace it with this server's address first." >&2
    exit 1
  fi
}

wait_api() {
  echo -n "Waiting for the database and API"
  for _ in $(seq 1 60); do
    if "${COMPOSE[@]}" exec -T backend python -c "import app.main" >/dev/null 2>&1; then echo " ok"; return 0; fi
    echo -n "."; sleep 3
  done
  echo; echo "The API container did not start — check ./uat.sh logs" >&2; exit 1
}

migrate() { "${COMPOSE[@]}" exec -T backend alembic upgrade head; }
seed() { "${COMPOSE[@]}" exec -T backend python -m app.seed_uat; }

urls() {
  host=$(grep -E '^APP_BASE_URL=' .env | cut -d= -f2- | sed -E 's#https?://##; s#:.*##')
  echo
  echo "Pensionz UAT:  http://$host:5178   (logins in UAT.md)"
  echo "Mailpit:       http://$host:8026   (sign-in codes and every email the app sends)"
  echo "API docs:      http://$host:8002/docs"
}

case "${1:-}" in
  install)
    need_env
    "${COMPOSE[@]}" up -d --build
    wait_api; migrate; seed; urls ;;
  update)
    need_env
    "${COMPOSE[@]}" up -d --build
    wait_api; migrate; urls ;;
  seed)
    seed ;;
  reset)
    need_env
    read -r -p "This deletes ALL UAT data (database and uploaded documents). Type RESET to continue: " answer
    [ "$answer" = "RESET" ] || { echo "Cancelled."; exit 1; }
    "${COMPOSE[@]}" down -v
    "${COMPOSE[@]}" up -d --build
    wait_api; migrate; seed; urls ;;
  status)
    "${COMPOSE[@]}" ps; urls ;;
  logs)
    "${COMPOSE[@]}" logs -f --tail=100 backend worker ;;
  stop)
    "${COMPOSE[@]}" stop ;;
  *)
    sed -n '2,12p' "$0"; exit 1 ;;
esac
