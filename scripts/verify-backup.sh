#!/usr/bin/env sh
set -eu

backup="${1:?Usage: verify-backup.sh /absolute/path/to/backup}"
case "$backup" in /*) ;; *) echo "Backup path must be absolute" >&2; exit 2;; esac
test -f "$backup/SHA256SUMS"
(cd "$backup" && sha256sum -c SHA256SUMS)
docker run --rm --read-only --network none -v "$backup:/backup:ro" postgres:16-alpine \
  pg_restore --list /backup/database.dump >/dev/null
docker run --rm --read-only --network none -v "$backup:/backup:ro" alpine:3.22 \
  tar -tzf /backup/attachments.tar.gz >/dev/null
printf 'Backup checksums and archive structures verified: %s\n' "$backup"
