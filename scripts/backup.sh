#!/usr/bin/env bash
#
# kataloghub.se site — timestamped full backup.
#
# Captures:
#   code/      project tree (excludes .venv, __pycache__, logs, backups, celerybeat-schedule)
#   postgres/  heyroya database (pg_dump plain SQL, --no-owner --no-acl)
#   minio/     MinIO bucket mirror (kataloghub-automation), via boto3
#   system/    nginx site config + systemd unit files
#
# Output:    /opt/kataloghub-automation/backups/kataloghub-YYYYMMDD-HHMMSS.tar.gz (mode 600)
# Retention: keeps the last $RETENTION_DAYS days, prunes older backups locally.
#
# Run via cron as root:
#   30 3 * * * /opt/kataloghub-automation/scripts/backup.sh >> /opt/kataloghub-automation/logs/backup.log 2>&1

set -euo pipefail

PROJECT_DIR="/opt/kataloghub-automation"
VENV_DIR="$PROJECT_DIR/.venv"
BACKUP_DIR="$PROJECT_DIR/backups"
LOGS_DIR="$PROJECT_DIR/logs"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

TS="$(date -u +%Y%m%d-%H%M%S)"
STAGE="$(mktemp -d /tmp/kataloghub-backup.XXXXXX)"
OUT="$BACKUP_DIR/kataloghub-$TS.tar.gz"

mkdir -p "$BACKUP_DIR" "$LOGS_DIR"
trap 'rm -rf "$STAGE"' EXIT

# Load .env (DATABASE_URL, MINIO_*, etc.)
set -a
# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"
set +a

step() { echo; echo "==> $1"; }

step "Archiving code tree"
mkdir -p "$STAGE/code"
# Two-stage tar avoids GNU-vs-BSD --transform/-X quirks.
tar -cf - \
  --exclude='./backups' \
  --exclude='./.venv' \
  --exclude='./.pytest_cache' \
  --exclude='./node_modules' \
  --exclude='./logs' \
  --exclude='./celerybeat-schedule' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -C "$PROJECT_DIR" . \
  | tar -xf - -C "$STAGE/code"

step "Dumping Postgres heyroya database"
mkdir -p "$STAGE/postgres"
sudo -u postgres pg_dump --format=plain --no-owner --no-acl heyroya \
  > "$STAGE/postgres/heyroya.sql"

step "Snapshotting MinIO bucket via boto3"
mkdir -p "$STAGE/minio"
export STAGE_MINIO="$STAGE/minio"
if "$VENV_DIR/bin/python" - <<'PY'
import os, sys
from pathlib import Path
try:
    import boto3
except Exception as e:
    print("boto3 not available:", e, file=sys.stderr); sys.exit(1)
client = boto3.client(
    "s3",
    endpoint_url=os.environ["MINIO_ENDPOINT"],
    aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
    aws_secret_access_key=os.environ["MINIO_SECRET_KEY"],
    region_name=os.environ.get("MINIO_REGION", "us-east-1"),
)
bucket = os.environ["MINIO_BUCKET"]
out = Path(os.environ["STAGE_MINIO"])
n = 0
paginator = client.get_paginator("list_objects_v2")
for page in paginator.paginate(Bucket=bucket):
    for obj in page.get("Contents", []):
        key = obj["Key"]
        target = out / key
        target.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, key, str(target))
        n += 1
print(f"    {n} object(s) downloaded from bucket {bucket}")
PY
then :
else
  echo "    (MinIO snapshot failed — continuing with the rest of the backup)"
fi

step "Capturing nginx + systemd configs"
mkdir -p "$STAGE/system"
for f in \
  /etc/nginx/sites-available/automation \
  /etc/systemd/system/kataloghub-api.service \
  /etc/systemd/system/kataloghub-worker.service \
  /etc/systemd/system/kataloghub-beat.service \
  /etc/systemd/system/minio.service ; do
  if [ -f "$f" ]; then cp "$f" "$STAGE/system/$(basename "$f")"; fi
done

step "Writing manifest"
GIT_HEAD="$(cd "$PROJECT_DIR" && git rev-parse HEAD 2>/dev/null || echo "n/a")"
GIT_REF="$(cd "$PROJECT_DIR" && git symbolic-ref --short HEAD 2>/dev/null || echo "n/a")"
cat > "$STAGE/MANIFEST.txt" <<EOF
kataloghub.se site backup
generated:    $TS (UTC)
host:         $(hostname -f)
git HEAD:     $GIT_HEAD
git ref:      $GIT_REF
retention:    $RETENTION_DAYS days
contents:
  code/       project tree (excludes .venv, __pycache__, logs, backups, celerybeat-schedule)
  postgres/   heyroya database (pg_dump --format=plain --no-owner --no-acl)
  minio/      MinIO bucket mirror ($MINIO_BUCKET)
  system/     nginx site config + systemd unit files
EOF

step "Building $OUT"
tar -czf "$OUT" -C "$STAGE" .
chmod 600 "$OUT"
ls -la "$OUT"

step "Pruning backups older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -name 'kataloghub-*.tar.gz' -mtime "+$RETENTION_DAYS" -print -delete || true

step "Done — $OUT"
