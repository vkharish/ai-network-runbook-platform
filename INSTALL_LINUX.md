# Linux Box Installation Guide
## AI Network Runbook Platform — Install alongside NetBox

---

## Overview

This guide installs the Runbook Platform on the same Linux box where NetBox is running.
Infrastructure (PostgreSQL, Redis, ChromaDB) runs as Docker containers alongside NetBox.
The API and Celery worker run as native Python processes (no Docker needed for them).

```
Linux Box
├── NetBox (Docker — already running)
├── runbook_postgres  (Docker — new, different port if needed)
├── runbook_redis     (Docker — new, different port if needed)
├── runbook_chroma    (Docker — new)
├── Runbook API       (native Python — port 8000)
└── Runbook Worker    (native Python — Celery)
```

Access from Windows via SSH tunnel (same as NetBox):
```
Windows → SSH tunnel :8000 → Linux :8000 (Runbook API)
Windows → SSH tunnel :8080 → Linux :80   (NetBox — existing)
```

---

## STEP 1 — Check Existing NetBox Docker Ports

Run this first to see what ports are already in use:

```bash
# Show all running containers and their ports
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"
```

Pay attention to these ports — we need to avoid clashing:

| Port | Typically Used By |
|------|------------------|
| 5432 | PostgreSQL |
| 6379 | Redis |
| 80 / 8080 | NetBox web UI |

**Check specifically:**
```bash
# Check if postgres port is taken
docker ps | grep 5432

# Check if redis port is taken
docker ps | grep 6379

# Check NetBox's internal network
docker network ls
docker inspect netbox_default 2>/dev/null | grep -E "Subnet|Gateway" || \
docker inspect $(docker network ls -q) | grep -A5 "netbox"
```

Note the results — you will use them in STEP 4.

---

## STEP 2 — Install System Dependencies

```bash
# Update package list
sudo apt update

# Python 3.11+ (check first)
python3 --version

# If below 3.11, install it
sudo apt install -y python3.11 python3.11-venv python3.11-pip

# Other required packages
sudo apt install -y git curl build-essential libpq-dev

# Verify
python3 --version
git --version
docker --version
```

---

## STEP 3 — Clone the Repository

```bash
cd ~
git clone https://github.com/vkharish/ai-network-runbook-platform.git
cd ai-network-runbook-platform
```

---

## STEP 4 — Handle Port Conflicts

Based on what you found in STEP 1, choose one of these options:

### Option A — No conflicts (ports 5432 and 6379 are free)

No changes needed. Skip to STEP 5.

### Option B — PostgreSQL port 5432 is taken by NetBox

Edit `docker/docker-compose.yml`:
```yaml
postgres:
  ports:
    - "5433:5432"    # change 5432 → 5433
```

### Option C — Redis port 6379 is taken by NetBox

Edit `docker/docker-compose.yml`:
```yaml
redis:
  ports:
    - "6380:6379"    # change 6379 → 6380
```

### Option D — Both ports are taken

```yaml
postgres:
  ports:
    - "5433:5432"
redis:
  ports:
    - "6380:6379"
```

**Quick edit command if needed:**
```bash
# Edit the compose file
nano docker/docker-compose.yml
```

---

## STEP 5 — Start Platform Infrastructure

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis chromadb
```

Verify all 3 are running:
```bash
docker ps | grep runbook
```

You should see:
```
runbook_postgres   Up (healthy)
runbook_redis      Up
runbook_chroma     Up
```

Wait for PostgreSQL to be ready:
```bash
until docker exec runbook_postgres pg_isready -U runbook; do
  echo "Waiting for postgres..."
  sleep 2
done
echo "PostgreSQL ready"
```

---

## STEP 6 — Create Virtual Environment

```bash
cd ~/ai-network-runbook-platform

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Verify key packages installed:
```bash
pip show fastapi netmiko paramiko anthropic
```

---

## STEP 7 — Configure .env

```bash
cp .env.example .env
nano .env
```

Set these values (adjust ports if you changed them in STEP 4):

```bash
# ── App ────────────────────────────────────────────────────────
APP_SECRET_KEY=$(openssl rand -hex 32)            # paste the output here (JWT signing)
CREDENTIAL_ENCRYPTION_KEY=$(openssl rand -hex 32) # paste a DIFFERENT value here (device password encryption)
APP_ENV=production

# ── Database ────────────────────────────────────────────────────
# Use 5433 if you changed the postgres port in STEP 4
DATABASE_URL=postgresql+asyncpg://runbook:runbook@localhost:5432/runbook_db

# ── Redis ───────────────────────────────────────────────────────
# Use 6380 if you changed the redis port in STEP 4
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ── ChromaDB ────────────────────────────────────────────────────
CHROMA_HOST=localhost
CHROMA_PORT=8001

# ── LLM ─────────────────────────────────────────────────────────
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5-20251001

# ── Embeddings ──────────────────────────────────────────────────
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

# ── NetBox ──────────────────────────────────────────────────────
# Run: docker ps | grep netbox  — to find the exact port
NETBOX_URL=http://localhost:80
NETBOX_TOKEN=your-netbox-api-token
```

**Generate both secret keys (run twice — use different values for each):**
```bash
openssl rand -hex 32
# Copy output → paste as APP_SECRET_KEY in .env

openssl rand -hex 32
# Copy output → paste as CREDENTIAL_ENCRYPTION_KEY in .env
# IMPORTANT: must be different from APP_SECRET_KEY
```

**Find NetBox port:**
```bash
docker ps | grep netbox | grep -oP '0.0.0.0:\K[0-9]+(?=->80)'
```

---

## STEP 8 — Run Database Migrations

```bash
source .venv/bin/activate
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade -> xxxx, initial schema
INFO  [alembic.runtime.migration] Running upgrade xxxx -> yyyy, add devices
...
```

---

## STEP 9 — Run the Test Suite

Confirm everything is wired up correctly before starting:

```bash
source .venv/bin/activate
python3 -m pytest tests/ -v
```

Expected: **49 passed, 0 failed**

---

## STEP 10 — Start the API

**Option A — Foreground (to verify it works first):**
```bash
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Test it: `curl http://localhost:8000/health`
Should return: `{"status": "ok"}`

Press Ctrl+C then move to Option B for permanent running.

**Option B — Background (using manage.sh):**
```bash
chmod +x scripts/manage.sh
./scripts/manage.sh start api
```

---

## STEP 11 — Start the Celery Worker and Beat Scheduler

```bash
# Clear corporate proxy if set (breaks LLM API calls)
unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY

# Worker (handles diagnosis + remediation execution tasks)
./scripts/manage.sh start worker

# Beat scheduler (runs continuous health monitoring every 5 minutes)
# Run in a separate terminal
source .venv/bin/activate
celery -A backend.tasks.celery_worker beat --loglevel=info
```

The Beat scheduler is optional — only needed if you want automatic anomaly
detection on live devices. Skip it if all devices are in simulator mode.

---

## STEP 12 — Check Everything is Running

```bash
./scripts/manage.sh status
```

Expected output:
```
[OK]  postgres    running (health: healthy)
[OK]  redis       running
[OK]  chromadb    running
[OK]  api         running (pid XXXX) — http://localhost:8000
[OK]  worker      running (pid XXXX) — queue depth: 0
```

---

## STEP 13 — Access from Windows via SSH Tunnel

On your Windows machine, add the Runbook API tunnel alongside your existing NetBox tunnel.

**Windows Terminal / PowerShell:**
```powershell
# Both NetBox and Runbook API in one command
# Adjust NetBox port (80) to match your actual NetBox port
ssh -L 8080:localhost:80 -L 8000:localhost:8000 user@linux-box-ip
```

**PuTTY:**
- Connection → SSH → Tunnels
- Add: Source=8000, Destination=localhost:8000, Local
- Save session

**MobaXterm:**
- Tunneling → New SSH Tunnel
- Local port: 8000, Remote: localhost:8000

Then open in browser:
- NetBox: `http://localhost:8080`
- Runbook Swagger: `http://localhost:8000/docs`
- Runbook Health: `http://localhost:8000/health`

---

## STEP 14 — Register Admin User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@youroffice.com",
    "password": "yourpassword",
    "full_name": "Admin",
    "role": "admin"
  }'
```

---

## STEP 15 — Sync Your NetBox Devices

You have 8-9 devices already in NetBox. Sync them all:

```bash
source .venv/bin/activate

# Dry run first — see what will be imported
python3 scripts/sync_netbox.py \
  --netbox-url http://localhost:80 \
  --netbox-token your-netbox-api-token \
  --runbook-email admin@youroffice.com \
  --runbook-password yourpassword \
  --live \
  --dry-run

# If output looks correct, run for real
python3 scripts/sync_netbox.py \
  --netbox-url http://localhost:80 \
  --netbox-token your-netbox-api-token \
  --runbook-email admin@youroffice.com \
  --runbook-password yourpassword \
  --live
```

Verify devices were imported:
```bash
curl -s http://localhost:8000/api/v1/devices/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | grep hostname
```

---

## STEP 16 — Set Device Credentials

For each device synced from NetBox, set the SSH password
(NetBox stores credentials separately — we need to set them here):

```bash
# Get token first
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@youroffice.com","password":"yourpassword"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Get device list with IDs
curl -s http://localhost:8000/api/v1/devices/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Set credentials per device (repeat for each device)
curl -X POST http://localhost:8000/api/v1/devices/<device-id>/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "router-ssh-password"}'
```

---

## STEP 17 — Test SSH to a Real Device

```bash
curl -X POST http://localhost:8000/api/v1/devices/<device-id>/test \
  -H "Authorization: Bearer $TOKEN"
```

Expected:
```json
{
  "success": true,
  "message": "Connection successful",
  "output_preview": "Cisco IOS XR Software, Version..."
}
```

---

## STEP 18 — Create and Diagnose a Real Incident

```bash
# Create incident
curl -X POST http://localhost:8000/api/v1/incidents/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "BGP session down on R1-CORE",
    "description": "BGP peer unreachable, session stuck in Active state",
    "severity": "P2",
    "affected_device": "R1-CORE",
    "affected_protocol": "bgp"
  }'

# Trigger AI diagnosis (use incident id from above response)
curl -X POST http://localhost:8000/api/v1/incidents/<incident-id>/diagnose \
  -H "Authorization: Bearer $TOKEN"

# Poll for result (wait ~30 seconds)
curl http://localhost:8000/api/v1/incidents/<incident-id> \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## Daily Operations

```bash
cd ~/ai-network-runbook-platform

# Start everything
./scripts/manage.sh start all

# Check status
./scripts/manage.sh status

# Stop everything
./scripts/manage.sh stop all

# View API logs
./scripts/manage.sh logs api

# View worker logs
./scripts/manage.sh logs worker

# Re-sync NetBox devices (run after adding new devices in NetBox)
source .venv/bin/activate
python3 scripts/sync_netbox.py \
  --netbox-url http://localhost:80 \
  --netbox-token your-token \
  --runbook-email admin@youroffice.com \
  --runbook-password yourpassword \
  --live
```

---

## Auto-Start on Linux Boot (Optional)

```bash
# Create systemd service for API
sudo nano /etc/systemd/system/runbook-api.service
```

```ini
[Unit]
Description=AI Network Runbook API
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=YOUR_LINUX_USERNAME
WorkingDirectory=/home/YOUR_LINUX_USERNAME/ai-network-runbook-platform
EnvironmentFile=/home/YOUR_LINUX_USERNAME/ai-network-runbook-platform/.env
ExecStart=/home/YOUR_LINUX_USERNAME/ai-network-runbook-platform/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Create systemd service for Celery worker
sudo nano /etc/systemd/system/runbook-worker.service
```

```ini
[Unit]
Description=AI Network Runbook Celery Worker
After=network.target runbook-api.service

[Service]
Type=simple
User=YOUR_LINUX_USERNAME
WorkingDirectory=/home/YOUR_LINUX_USERNAME/ai-network-runbook-platform
EnvironmentFile=/home/YOUR_LINUX_USERNAME/ai-network-runbook-platform/.env
Environment=HTTP_PROXY=
Environment=HTTPS_PROXY=
ExecStart=/home/YOUR_LINUX_USERNAME/ai-network-runbook-platform/.venv/bin/celery -A backend.tasks.celery_worker worker --loglevel=info --pool=solo
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable runbook-api runbook-worker
sudo systemctl start runbook-api runbook-worker

# Check status
sudo systemctl status runbook-api
sudo systemctl status runbook-worker
```

---

## Secret Key Management

The platform uses **two separate keys** in `.env`:

| Key | Purpose | Impact if rotated |
|-----|---------|------------------|
| `APP_SECRET_KEY` | Signs JWT login tokens | All active sessions invalidated — users re-login |
| `CREDENTIAL_ENCRYPTION_KEY` | Encrypts device/jump host SSH passwords at rest | Must run migration script before rotating |

### When to Rotate

**Rotate `CREDENTIAL_ENCRYPTION_KEY` when:**
- Someone who had access to `.env` leaves your team
- The key was accidentally exposed (git commit, log file, screen share)
- The Linux box is suspected compromised
- Promoting from lab to production (start fresh before entering real passwords)

**Rotate `APP_SECRET_KEY` when:**
- Key was exposed and you want to invalidate all active sessions immediately

**For a small internal lab — you may never need to rotate at all.**

### How to Rotate CREDENTIAL_ENCRYPTION_KEY

```bash
cd ~/ai-network-runbook-platform
source .venv/bin/activate

# Step 1 — dry run first (no DB changes)
OLD_CREDENTIAL_KEY="<paste old key here>" \
  python3 scripts/rotate_credential_key.py --dry-run

# Step 2 — if output looks correct, run for real
OLD_CREDENTIAL_KEY="<paste old key here>" \
  python3 scripts/rotate_credential_key.py

# Step 3 — update .env with the new key
nano .env   # set CREDENTIAL_ENCRYPTION_KEY=<new value>

# Step 4 — restart services
./scripts/manage.sh stop all
./scripts/manage.sh start all
```

The script re-encrypts all stored device credentials and jump host passwords
from the old key to the new key. No data is lost.

### How to Rotate APP_SECRET_KEY

```bash
# Generate new key
openssl rand -hex 32

# Paste into .env as APP_SECRET_KEY, then restart
./scripts/manage.sh stop all
./scripts/manage.sh start all
# All users will be logged out — they re-login normally
```

---

## Troubleshooting

| Problem | Command | Fix |
|---------|---------|-----|
| Port clash with NetBox | `docker ps \| grep 5432` | Change port in docker-compose.yml |
| API won't start | `./scripts/manage.sh logs api` | Check .env values |
| Worker crashes | `./scripts/manage.sh logs worker` | Unset proxy vars |
| Migration fails | `alembic upgrade head` | Check DATABASE_URL in .env |
| Device SSH fails | Check `/api/v1/devices/{id}/test` | Verify host IP reachable from Linux box |
| NetBox sync fails | Add `--dry-run` first | Check NETBOX_TOKEN and NETBOX_URL |
| ChromaDB error | `docker logs runbook_chroma` | Restart: `docker restart runbook_chroma` |

---

## Summary Checklist

- [ ] STEP 1  — Checked existing NetBox Docker ports
- [ ] STEP 2  — Installed system dependencies
- [ ] STEP 3  — Cloned repository
- [ ] STEP 4  — Resolved port conflicts (if any)
- [ ] STEP 5  — Started Docker infrastructure
- [ ] STEP 6  — Created Python virtual environment
- [ ] STEP 7  — Configured .env
- [ ] STEP 8  — Run database migrations
- [ ] STEP 9  — Run test suite (49/49 passing)
- [ ] STEP 10 — Started API
- [ ] STEP 11 — Started Celery worker
- [ ] STEP 12 — Verified status
- [ ] STEP 13 — SSH tunnel working from Windows
- [ ] STEP 14 — Admin user registered
- [ ] STEP 15 — NetBox devices synced (8-9 devices)
- [ ] STEP 16 — Device credentials set
- [ ] STEP 17 — SSH connection test passed
- [ ] STEP 18 — First real incident diagnosed
