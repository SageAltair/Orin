#!/usr/bin/env sh
set -eu

backup="${1:?Usage: restore-drill.sh /absolute/path/to/backup}"
case "$backup" in /*) ;; *) echo "Backup path must be absolute" >&2; exit 2;; esac
sh "$(dirname "$0")/verify-backup.sh" "$backup"
name="orin-restore-drill-$$"
attachment_volume="$name-attachments"
keys_file="$(mktemp)"
cleanup() {
  rm -f "$keys_file"
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm -f "$attachment_volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
docker run -d --name "$name" --network none --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,nodev,size=1g \
  -e POSTGRES_PASSWORD=restore-drill-only postgres:16-alpine >/dev/null
i=0
until docker exec "$name" pg_isready -U postgres >/dev/null 2>&1; do
  i=$((i + 1)); test "$i" -lt 30 || { echo "Restore drill database did not become ready" >&2; exit 1; }
  sleep 1
done
docker cp "$backup/database.dump" "$name:/tmp/database.dump"
docker exec "$name" pg_restore --exit-on-error --no-owner -U postgres -d postgres /tmp/database.dump
revision="$(docker exec "$name" psql -At -U postgres -d postgres -c 'select version_num from alembic_version')"
test -n "$revision" || { echo "Restored database has no Alembic revision" >&2; exit 1; }
docker exec "$name" psql -At -U postgres -d postgres -c 'select storage_key from file_attachments order by storage_key' > "$keys_file"
docker volume create "$attachment_volume" >/dev/null
docker run --rm --network none \
  -v "$backup:/backup:ro" -v "$keys_file:/attachment-keys:ro" -v "$attachment_volume:/restore" \
  alpine:3.22 sh -eu -c '
    tar -C /restore -xzf /backup/attachments.tar.gz
    chown -R 10001:10001 /restore
    while IFS= read -r key; do test -z "$key" || test -f "/restore/$key"; done < /attachment-keys
    test "$(find /restore -type f ! -user 10001 -print -quit)" = ""
  '
printf 'Isolated database and attachment restore drill passed at Alembic revision %s\n' "$revision"
