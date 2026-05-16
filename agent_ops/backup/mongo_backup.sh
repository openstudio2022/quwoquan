#!/usr/bin/env bash
set -euo pipefail

MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/mongodb}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DATE=$(date +%Y%m%d_%H%M%S)
TARGET="$BACKUP_DIR/$DATE"

mkdir -p "$TARGET"

echo "[mongo_backup] Starting at $(date) -> $TARGET"
mongodump --uri="$MONGO_URI" --out="$TARGET" --gzip

echo "[mongo_backup] Dump complete. Cleaning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf {} +

echo "[mongo_backup] Done at $(date)"
