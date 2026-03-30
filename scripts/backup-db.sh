#!/usr/bin/env bash
#
# Database backup script for the Professor system.
#
# Usage:
#   ./scripts/backup-db.sh              # Manual backup
#   0 3 * * * /path/to/backup-db.sh     # Cron: daily at 3 AM
#
# Retention policy:
#   - Daily backups kept for 7 days
#   - Weekly backups (Sunday) kept for 4 weeks
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/backups"
CONTAINER_NAME="${POSTGRES_CONTAINER:-professor-postgres}"
DB_NAME="${POSTGRES_DB:-professor}"
DB_USER="${POSTGRES_USER:-professor}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DAY_OF_WEEK="$(date +%u)"  # 1=Monday ... 7=Sunday

mkdir -p "$BACKUP_DIR"

BACKUP_FILE="${BACKUP_DIR}/professor_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting backup → ${BACKUP_FILE}"

docker exec "$CONTAINER_NAME" \
  pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges \
  | gzip > "$BACKUP_FILE"

BACKUP_SIZE="$(du -h "$BACKUP_FILE" | cut -f1)"
echo "[$(date)] Backup complete: ${BACKUP_SIZE}"

# Tag weekly backups (Sunday = 7) by creating a symlink
if [ "$DAY_OF_WEEK" = "7" ]; then
  WEEKLY_LINK="${BACKUP_DIR}/weekly_${TIMESTAMP}.sql.gz"
  ln -sf "$(basename "$BACKUP_FILE")" "$WEEKLY_LINK"
  echo "[$(date)] Tagged as weekly backup"
fi

# Prune daily backups older than 7 days (skip weekly symlinks)
find "$BACKUP_DIR" -maxdepth 1 -name "professor_*.sql.gz" -mtime +7 -type f -delete
echo "[$(date)] Pruned daily backups older than 7 days"

# Prune weekly backups older than 28 days
find "$BACKUP_DIR" -maxdepth 1 -name "weekly_*.sql.gz" -mtime +28 -type l -delete
echo "[$(date)] Pruned weekly backups older than 28 days"

echo "[$(date)] Backup pipeline finished"
