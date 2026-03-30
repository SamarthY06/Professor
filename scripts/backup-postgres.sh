#!/bin/bash
# PostgreSQL backup script for Professor
# Schedule via cron: 0 2 * * * /path/to/backup-postgres.sh

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
DB_CONTAINER="${DB_CONTAINER:-professor-postgres-1}"
DB_NAME="${POSTGRES_DB:-professor}"
DB_USER="${POSTGRES_USER:-professor}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/professor_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting PostgreSQL backup..."

docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --format=plain \
  | gzip > "$BACKUP_FILE"

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup created: $BACKUP_FILE ($BACKUP_SIZE)"

# Clean up old backups
echo "[$(date)] Cleaning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "professor_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete

REMAINING=$(ls -1 "$BACKUP_DIR"/professor_*.sql.gz 2>/dev/null | wc -l)
echo "[$(date)] Backup complete. $REMAINING backups retained."
