#!/usr/bin/env bash
# manage.sh — Start, stop, status, and debug each module individually
# Usage: ./scripts/manage.sh <command> [module]
#
# Modules: api | worker | frontend | ollama | postgres | redis | chromadb | all
# Commands: start | stop | restart | status | logs | debug

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# ── Color helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()     { echo -e "${RED}[ERROR]${NC} $*"; }

# ── PID helpers ────────────────────────────────────────────────────────────
pid_of_api()      { pgrep -f "uvicorn backend.main" 2>/dev/null | head -1 || true; }
pid_of_worker()   { pgrep -f "celery.*backend.tasks.celery_worker" 2>/dev/null | grep -v " T " | head -1 || true; }
pid_of_frontend() { pgrep -f "vite" 2>/dev/null | head -1 || true; }
pid_of_ollama()   { pgrep -f "ollama serve" 2>/dev/null | head -1 || true; }

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

# ── Status check ──────────────────────────────────────────────────────────
check_status() {
  echo ""
  echo "══════════════════════════════════════════"
  echo "   AI Runbook Platform — Module Status"
  echo "══════════════════════════════════════════"

  # Docker services
  for svc in runbook_postgres runbook_redis runbook_chroma; do
    local state
    state=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "not found")
    local health
    health=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "")
    local name="${svc#runbook_}"
    if [[ "$state" == "running" ]]; then
      ok "  $name     running ${health:+(health: $health)}"
    else
      err "  $name     $state"
    fi
  done

  # API
  local api_pid; api_pid=$(pid_of_api)
  if is_running "$api_pid"; then
    local api_resp; api_resp=$(curl -s --max-time 2 http://localhost:8000/health 2>/dev/null || echo "timeout")
    if echo "$api_resp" | grep -q "ok"; then
      ok "  api        running  (pid $api_pid) — http://localhost:8000"
    else
      warn "  api        process up (pid $api_pid) but /health not responding"
    fi
  else
    err "  api        stopped"
  fi

  # Worker
  local worker_pid; worker_pid=$(pid_of_worker)
  if is_running "$worker_pid"; then
    local qlen; qlen=$(docker exec runbook_redis redis-cli LLEN celery 2>/dev/null || echo "?")
    ok "  worker     running  (pid $worker_pid) — queue depth: $qlen"
  else
    err "  worker     stopped"
  fi

  # Frontend
  local fe_pid; fe_pid=$(pid_of_frontend)
  if is_running "$fe_pid"; then
    ok "  frontend   running  (pid $fe_pid) — http://localhost:5173"
  else
    warn "  frontend   stopped  (optional for API-only use)"
  fi

  # Ollama
  local ol_pid; ol_pid=$(pid_of_ollama)
  if is_running "$ol_pid"; then
    local models; models=$(curl -s --max-time 2 http://localhost:11434/api/tags 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(m['name'] for m in d.get('models',[])))" 2>/dev/null || echo "unknown")
    ok "  ollama     running  (pid $ol_pid) — models: $models"
  else
    warn "  ollama     stopped  (only needed if LLM_PROVIDER=ollama)"
  fi

  # DB check
  echo ""
  echo "── Database ──────────────────────────────"
  local inc_count; inc_count=$(docker exec runbook_postgres psql -U runbook -d runbook_db -t -c "SELECT count(*) FROM incidents;" 2>/dev/null | tr -d ' \n' || echo "?")
  local dev_count; dev_count=$(docker exec runbook_postgres psql -U runbook -d runbook_db -t -c "SELECT count(*) FROM devices;" 2>/dev/null | tr -d ' \n' || echo "?")
  local user_count; user_count=$(docker exec runbook_postgres psql -U runbook -d runbook_db -t -c "SELECT count(*) FROM users;" 2>/dev/null | tr -d ' \n' || echo "?")
  info "  incidents=$inc_count  devices=$dev_count  users=$user_count"

  echo ""
  echo "── Blocked DB connections ────────────────"
  local blocked; blocked=$(docker exec runbook_postgres psql -U runbook -d runbook_db -t -c "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND datname='runbook_db';" 2>/dev/null | tr -d ' \n' || echo "?")
  if [[ "$blocked" == "0" ]]; then
    ok "  no blocked queries"
  else
    err "  $blocked blocked queries — run: ./scripts/manage.sh debug db"
  fi
  echo ""
}

# ── Start ──────────────────────────────────────────────────────────────────
start_module() {
  local module="$1"
  case "$module" in
    postgres|redis|chromadb)
      info "Starting $module..."
      docker compose -f docker/docker-compose.yml up -d "$module" 2>/dev/null || \
        docker compose -f docker/docker-compose.yml up -d "runbook_$module" 2>/dev/null || true
      ok "$module started"
      ;;
    api)
      if is_running "$(pid_of_api)"; then warn "API already running (pid $(pid_of_api))"; return; fi
      info "Starting API..."
      nohup .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload \
        > /tmp/runbook_api.log 2>&1 &
      sleep 2
      if is_running "$(pid_of_api)"; then
        ok "API started (pid $(pid_of_api)) — logs: tail -f /tmp/runbook_api.log"
      else
        err "API failed to start — check: tail -20 /tmp/runbook_api.log"
      fi
      ;;
    worker)
      if is_running "$(pid_of_worker)"; then warn "Worker already running (pid $(pid_of_worker))"; return; fi
      # Kill any suspended (Ctrl+Z) worker processes first
      pkill -f "celery.*backend.tasks.celery_worker" 2>/dev/null || true
      sleep 1
      info "Starting Celery worker..."
      unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY
      OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES nohup .venv/bin/celery \
        -A backend.tasks.celery_worker worker --loglevel=info --pool=solo \
        > /tmp/runbook_worker.log 2>&1 &
      sleep 2
      if is_running "$(pid_of_worker)"; then
        ok "Worker started (pid $(pid_of_worker)) — logs: tail -f /tmp/runbook_worker.log"
      else
        err "Worker failed to start — check: tail -20 /tmp/runbook_worker.log"
      fi
      ;;
    frontend)
      if is_running "$(pid_of_frontend)"; then warn "Frontend already running (pid $(pid_of_frontend))"; return; fi
      info "Starting frontend dev server..."
      nohup bash -c "cd frontend && npm run dev" > /tmp/runbook_frontend.log 2>&1 &
      sleep 3
      ok "Frontend started — http://localhost:5173 — logs: tail -f /tmp/runbook_frontend.log"
      ;;
    ollama)
      if is_running "$(pid_of_ollama)"; then warn "Ollama already running (pid $(pid_of_ollama))"; return; fi
      info "Starting Ollama..."
      nohup ollama serve > /tmp/runbook_ollama.log 2>&1 &
      sleep 2
      ok "Ollama started — logs: tail -f /tmp/runbook_ollama.log"
      ;;
    all)
      docker compose -f docker/docker-compose.yml up -d postgres redis chromadb
      start_module api
      start_module worker
      start_module frontend
      ;;
    *)
      err "Unknown module: $module"; usage; exit 1 ;;
  esac
}

# ── Stop ───────────────────────────────────────────────────────────────────
stop_module() {
  local module="$1"
  case "$module" in
    postgres|redis|chromadb)
      info "Stopping $module..."
      docker compose -f docker/docker-compose.yml stop "$module" 2>/dev/null || true
      ok "$module stopped"
      ;;
    api)
      local pid; pid=$(pid_of_api)
      if is_running "$pid"; then
        kill -9 "$pid" 2>/dev/null && ok "API stopped (was pid $pid)"
      else
        warn "API not running"
      fi
      ;;
    worker)
      info "Stopping all celery worker processes..."
      pkill -9 -f "celery.*backend.tasks.celery_worker" 2>/dev/null && ok "Worker stopped" || warn "Worker not running"
      ;;
    frontend)
      local pid; pid=$(pid_of_frontend)
      if is_running "$pid"; then
        kill -9 "$pid" 2>/dev/null && ok "Frontend stopped (was pid $pid)"
      else
        warn "Frontend not running"
      fi
      ;;
    ollama)
      local pid; pid=$(pid_of_ollama)
      if is_running "$pid"; then
        kill -9 "$pid" 2>/dev/null && ok "Ollama stopped (was pid $pid)"
      else
        warn "Ollama not running"
      fi
      ;;
    all)
      stop_module api
      stop_module worker
      stop_module frontend
      stop_module ollama
      docker compose -f docker/docker-compose.yml down
      ok "All modules stopped"
      ;;
    *)
      err "Unknown module: $module"; usage; exit 1 ;;
  esac
}

# ── Logs ───────────────────────────────────────────────────────────────────
show_logs() {
  local module="$1"
  case "$module" in
    api)      tail -f /tmp/runbook_api.log ;;
    worker)   tail -f /tmp/runbook_worker.log ;;
    frontend) tail -f /tmp/runbook_frontend.log ;;
    ollama)   tail -f /tmp/runbook_ollama.log ;;
    postgres) docker logs -f runbook_postgres ;;
    redis)    docker logs -f runbook_redis ;;
    chromadb) docker logs -f runbook_chroma ;;
    *)        err "Unknown module: $module"; exit 1 ;;
  esac
}

# ── Debug ──────────────────────────────────────────────────────────────────
debug_module() {
  local module="$1"
  case "$module" in
    db)
      echo ""
      echo "── Active DB connections ─────────────────"
      docker exec runbook_postgres psql -U runbook -d runbook_db -c \
        "SELECT pid, state, wait_event_type, left(query,80) as query FROM pg_stat_activity WHERE datname='runbook_db' ORDER BY state;" 2>&1

      echo ""
      echo "── Blocked connections (Lock waits) ──────"
      local blocked
      blocked=$(docker exec runbook_postgres psql -U runbook -d runbook_db -t -c \
        "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND datname='runbook_db';" 2>/dev/null | tr -d ' \n')
      if [[ "$blocked" -gt 0 ]]; then
        warn "$blocked blocked queries found — killing them now..."
        docker exec runbook_postgres psql -U runbook -d runbook_db -c \
          "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='runbook_db' AND pid != pg_backend_pid() AND state = 'idle in transaction';" 2>&1
        ok "Idle-in-transaction connections terminated"
      else
        ok "No blocked queries"
      fi
      ;;
    incidents)
      echo ""
      docker exec runbook_postgres psql -U runbook -d runbook_db -c \
        "SELECT incident_number, left(title,40) as title, status, severity, created_at::date FROM incidents ORDER BY incident_number;" 2>&1
      ;;
    queue)
      echo ""
      info "Redis queue depth: $(docker exec runbook_redis redis-cli LLEN celery 2>/dev/null)"
      info "Redis keys:"
      docker exec runbook_redis redis-cli KEYS "*" 2>&1
      ;;
    api)
      echo ""
      info "Testing API endpoints..."
      echo -n "  /health       : "; curl -s --max-time 3 http://localhost:8000/health || echo "FAIL"
      echo -n "  /readiness    : "; curl -s --max-time 3 http://localhost:8000/readiness || echo "FAIL"
      echo -n "  /metrics      : "; curl -s --max-time 3 http://localhost:8000/metrics | grep "^rag_" | head -3 || echo "FAIL"
      ;;
    worker)
      echo ""
      info "Celery worker processes:"
      ps aux | grep "celery" | grep -v grep
      echo ""
      info "Queue depth: $(docker exec runbook_redis redis-cli LLEN celery 2>/dev/null)"
      ;;
    *)
      err "Unknown debug target: $module"
      echo "  Available: db | incidents | queue | api | worker"
      ;;
  esac
}

# ── Reset stuck incident ───────────────────────────────────────────────────
reset_incident() {
  local num="$1"
  docker exec runbook_postgres psql -U runbook -d runbook_db -c \
    "UPDATE incidents SET status='open', ai_report=NULL WHERE incident_number=$num;" 2>&1
  ok "INC-$(printf '%04d' "$num") reset to 'open'"
}

# ── Usage ──────────────────────────────────────────────────────────────────
usage() {
  echo ""
  echo "Usage: ./scripts/manage.sh <command> [module|target]"
  echo ""
  echo "Commands:"
  echo "  status                    — show all module status"
  echo "  start  <module>           — start a module"
  echo "  stop   <module>           — stop a module"
  echo "  restart <module>          — stop then start"
  echo "  logs   <module>           — tail logs"
  echo "  debug  <target>           — debug a specific area"
  echo "  reset-incident <number>   — reset stuck incident back to 'open'"
  echo ""
  echo "Modules:  api | worker | frontend | ollama | postgres | redis | chromadb | all"
  echo "Debug:    db | incidents | queue | api | worker"
  echo ""
  echo "Examples:"
  echo "  ./scripts/manage.sh status"
  echo "  ./scripts/manage.sh stop worker"
  echo "  ./scripts/manage.sh start worker"
  echo "  ./scripts/manage.sh restart api"
  echo "  ./scripts/manage.sh logs worker"
  echo "  ./scripts/manage.sh debug db"
  echo "  ./scripts/manage.sh debug incidents"
  echo "  ./scripts/manage.sh reset-incident 7"
  echo ""
}

# ── Main ───────────────────────────────────────────────────────────────────
CMD="${1:-help}"
MOD="${2:-}"

case "$CMD" in
  status)          check_status ;;
  start)           [[ -z "$MOD" ]] && { err "Specify module"; usage; exit 1; }; start_module "$MOD" ;;
  stop)            [[ -z "$MOD" ]] && { err "Specify module"; usage; exit 1; }; stop_module "$MOD" ;;
  restart)         [[ -z "$MOD" ]] && { err "Specify module"; usage; exit 1; }; stop_module "$MOD"; sleep 1; start_module "$MOD" ;;
  logs)            [[ -z "$MOD" ]] && { err "Specify module"; usage; exit 1; }; show_logs "$MOD" ;;
  debug)           [[ -z "$MOD" ]] && { err "Specify debug target"; usage; exit 1; }; debug_module "$MOD" ;;
  reset-incident)  [[ -z "$MOD" ]] && { err "Specify incident number"; exit 1; }; reset_incident "$MOD" ;;
  help|--help|-h)  usage ;;
  *)               err "Unknown command: $CMD"; usage; exit 1 ;;
esac
