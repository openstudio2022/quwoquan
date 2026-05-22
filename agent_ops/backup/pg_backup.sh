#!/usr/bin/env bash
set -euo pipefail

PG_DSN="${PG_DSN:-postgres://postgres:postgres@localhost:5432/quwoquan?sslmode=disable}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgresql}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="$BACKUP_DIR/pg_$DATE.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[pg_backup] Starting at $(date) -> $FILENAME"
pg_dump "$PG_DSN" | gzip > "$FILENAME"

echo "[pg_backup] Dump complete. Cleaning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -maxdepth 1 -name 'pg_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "[pg_backup] Done at $(date)"
