#!/usr/bin/env bash
#
# HeyRoya Automation — VPS bootstrap / deploy script.
# Idempotent: safe to re-run after edits or rollouts.
#
# Prerequisites (run these manually before this script):
#   1. SSH to VPS as root.
#   2. apt-get update && apt-get install -y git
#   3. git clone https://github.com/mrglennc64/auto.git /opt/heyroya-automation
#   4. cd /opt/heyroya-automation && bash scripts/deploy.sh
#
# After this script:
#   1. Edit /opt/heyroya-automation/.env with real secrets.
#   2. Re-run `bash scripts/deploy.sh restart` to pick up env changes.
#   3. Run `certbot --nginx -d automation.heyroya.se` for HTTPS.

set -euo pipefail

PROJECT_DIR="/opt/heyroya-automation"
VENV_DIR="$PROJECT_DIR/.venv"
SERVICE_NAMES=(heyroya-api heyroya-worker heyroya-beat)

step() { echo; echo "==> $1"; }

cmd="${1:-full}"

case "$cmd" in
  full)
    "$0" packages
    "$0" minio
    "$0" db
    "$0" venv
    "$0" env
    "$0" migrate
    "$0" services
    "$0" nginx
    "$0" firewall
    "$0" verify
    ;;

  packages)
    step "Installing system packages"
    apt-get update
    apt-get install -y \
      python3 python3-venv python3-pip \
      git curl ufw \
      nginx redis-server postgresql \
      certbot python3-certbot-nginx
    ;;

  minio)
    step "Installing MinIO binary + service"
    if [ ! -x /usr/local/bin/minio ]; then
      curl -L https://dl.min.io/server/minio/release/linux-amd64/minio -o /usr/local/bin/minio
      chmod +x /usr/local/bin/minio
    fi
    mkdir -p /var/lib/minio
    if [ ! -f /etc/default/minio ]; then
      echo "==> creating /etc/default/minio with random root credentials"
      MINIO_ROOT_USER="heyroya"
      MINIO_ROOT_PASSWORD="$(openssl rand -hex 24)"
      cat > /etc/default/minio <<EOF
MINIO_ROOT_USER=$MINIO_ROOT_USER
MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD
EOF
      chmod 600 /etc/default/minio
      echo "    MinIO credentials written to /etc/default/minio"
      echo "    user=$MINIO_ROOT_USER  password=$MINIO_ROOT_PASSWORD"
      echo "    --> COPY THESE into /opt/heyroya-automation/.env (MINIO_ACCESS_KEY / MINIO_SECRET_KEY)"
    fi
    cp "$PROJECT_DIR/systemd/minio.service" /etc/systemd/system/minio.service
    systemctl daemon-reload
    systemctl enable --now minio
    ;;

  db)
    step "Initializing Postgres user + database"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='heyroya'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE USER heyroya WITH PASSWORD 'heyroya-CHANGE-ME-after-creation';"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='heyroya'" | grep -q 1 \
      || sudo -u postgres psql -c "CREATE DATABASE heyroya OWNER heyroya;"
    echo "    --> CHANGE the heyroya db password:"
    echo "    sudo -u postgres psql -c \"ALTER USER heyroya WITH PASSWORD '<new-strong-password>';\""
    ;;

  venv)
    step "Creating Python venv + installing dependencies"
    if [ ! -d "$VENV_DIR" ]; then
      python3 -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
    ;;

  env)
    step "Generating .env template (only if absent)"
    if [ ! -f "$PROJECT_DIR/.env" ]; then
      API_KEY="$(openssl rand -hex 32)"
      DASHBOARD_PASS="$(openssl rand -hex 16)"
      cat > "$PROJECT_DIR/.env" <<EOF
DATABASE_URL=postgresql+psycopg://heyroya:CHANGE-ME-MATCH-PG-PASSWORD@localhost:5432/heyroya
REDIS_URL=redis://localhost:6379/0

MINIO_ENDPOINT=http://127.0.0.1:9000
MINIO_ACCESS_KEY=heyroya
MINIO_SECRET_KEY=CHANGE-ME-COPY-FROM-/etc/default/minio
MINIO_BUCKET=heyroya-automation
MINIO_REGION=us-east-1
PRESIGNED_URL_TTL_SECONDS=604800

RESEND_API_KEY=CHANGE-ME-from-resend.com
RESEND_FROM=HeyRoya <noreply@heyroya.se>
RESEND_OPERATOR_BCC=

API_KEYS=$API_KEY

DASHBOARD_USER=admin
DASHBOARD_PASS=$DASHBOARD_PASS

PUBLIC_BASE_URL=https://automation.heyroya.se
ENVIRONMENT=production
EOF
      chmod 600 "$PROJECT_DIR/.env"
      echo "    Generated $PROJECT_DIR/.env with random API_KEY and DASHBOARD_PASS."
      echo "    --> EDIT this file:  fill in DATABASE_URL password, MINIO_SECRET_KEY, RESEND_API_KEY"
      echo "    --> Then re-run:  bash scripts/deploy.sh restart"
    else
      echo "    .env already exists — leaving alone"
    fi
    ;;

  migrate)
    step "Running Alembic migrations"
    cd "$PROJECT_DIR"
    set -a; source "$PROJECT_DIR/.env"; set +a
    "$VENV_DIR/bin/alembic" upgrade head
    "$VENV_DIR/bin/python" -c "from app.services.storage import ensure_bucket; ensure_bucket(); print('MinIO bucket ready')"
    ;;

  services)
    step "Installing + starting systemd services"
    for svc in "${SERVICE_NAMES[@]}"; do
      cp "$PROJECT_DIR/systemd/$svc.service" "/etc/systemd/system/$svc.service"
    done
    systemctl daemon-reload
    for svc in "${SERVICE_NAMES[@]}"; do
      systemctl enable "$svc"
      systemctl restart "$svc"
    done
    ;;

  nginx)
    step "Installing nginx config (HTTP only — run certbot for HTTPS)"
    cp "$PROJECT_DIR/nginx/automation.heyroya.se.conf" /etc/nginx/sites-available/automation
    ln -sf /etc/nginx/sites-available/automation /etc/nginx/sites-enabled/automation
    nginx -t
    systemctl reload nginx
    echo "    --> Run:  certbot --nginx -d automation.heyroya.se"
    ;;

  firewall)
    step "Configuring UFW (allow 22, 80, 443; deny everything else)"
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
    ufw status
    ;;

  restart)
    step "Restarting services (after .env or code changes)"
    for svc in "${SERVICE_NAMES[@]}"; do
      systemctl restart "$svc"
      systemctl --no-pager status "$svc" | head -3
    done
    ;;

  pull)
    step "Pulling latest from origin/main + restart"
    cd "$PROJECT_DIR"
    git pull --ff-only
    "$VENV_DIR/bin/pip" install -r requirements.txt
    set -a; source "$PROJECT_DIR/.env"; set +a
    "$VENV_DIR/bin/alembic" upgrade head
    "$0" restart
    ;;

  verify)
    step "Verifying API + dashboard are reachable"
    sleep 2
    curl -fsS http://127.0.0.1:8000/api/health && echo
    echo "    --> Public check (after certbot):"
    echo "    curl -fsS https://automation.heyroya.se/api/health"
    ;;

  *)
    echo "Usage: $0 {full|packages|minio|db|venv|env|migrate|services|nginx|firewall|restart|pull|verify}"
    exit 1
    ;;
esac

echo
echo "==> Step '$cmd' complete."
