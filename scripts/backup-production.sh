#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT/docker-compose.production.yml"
BACKUP_ROOT="${BACKUP_DIRECTORY:?Set BACKUP_DIRECTORY to an absolute, protected, off-host-mounted directory}"
case "$BACKUP_ROOT" in /*) ;; *) echo "BACKUP_DIRECTORY must be absolute" >&2; exit 2;; esac
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_ROOT/$stamp"
mkdir -p "$target"

db_container="$(docker compose -f "$COMPOSE_FILE" ps -q db)"
api_container="$(docker compose -f "$COMPOSE_FILE" ps -q api)"
test -n "$db_container" || { echo "Production database is not running" >&2; exit 1; }
test -n "$api_container" || { echo "Production API is not running" >&2; exit 1; }
dump_path="/tmp/orin-$stamp.dump"
paused=0
cleanup() {
  docker exec "$db_container" rm -f "$dump_path" >/dev/null 2>&1 || true
  if test "$paused" = 1; then docker unpause "$api_container" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM
docker pause "$api_container" >/dev/null
paused=1
docker exec "$db_container" sh -eu -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$1"' sh "$dump_path"
docker cp "$db_container:$dump_path" "$target/database.dump"

attachment_volume="$(docker inspect "$api_container" --format '{{range .Mounts}}{{if eq .Destination "/app/data/attachments"}}{{.Name}}{{end}}{{end}}')"
test -n "$attachment_volume" || { echo "Could not resolve the API attachment volume" >&2; exit 1; }
docker run --rm --read-only --network none \
  -v "$attachment_volume:/source:ro" -v "$target:/backup" \
  alpine:3.22 tar -C /source -czf /backup/attachments.tar.gz .
docker unpause "$api_container" >/dev/null
paused=0

printf '%s\n' "$stamp" > "$target/created-at-utc.txt"
(cd "$target" && sha256sum database.dump attachments.tar.gz created-at-utc.txt > SHA256SUMS)
printf 'Backup created at %s\n' "$target"
printf 'Copy this directory to an encrypted off-host destination and run verify-backup.sh.\n'
