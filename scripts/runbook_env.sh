#!/usr/bin/env bash
# runbook_env.sh — Source this file once per terminal session.
#
# Usage:
#   source scripts/runbook_env.sh
#
# Token lasts 30 days (JWT_ACCESS_TOKEN_EXPIRE_MINUTES=43200 in .env).
# No caching needed — just login once and use $TOKEN for the month.

RUNBOOK_URL="${RUNBOOK_URL:-http://localhost:8000}"
RUNBOOK_EMAIL="${RUNBOOK_EMAIL:-}"
RUNBOOK_PASSWORD="${RUNBOOK_PASSWORD:-}"

# ── Credential resolution ─────────────────────────────────────────────────────
if [[ -z "$RUNBOOK_EMAIL" ]]; then
    read -rp "Runbook email: " RUNBOOK_EMAIL
fi
if [[ -z "$RUNBOOK_PASSWORD" ]]; then
    read -rsp "Runbook password: " RUNBOOK_PASSWORD
    echo
fi

# ── Login ─────────────────────────────────────────────────────────────────────
echo "[runbook_env] Logging in..."
TOKEN=$(curl -s -X POST "${RUNBOOK_URL}/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${RUNBOOK_EMAIL}\",\"password\":\"${RUNBOOK_PASSWORD}\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)

if [[ -z "$TOKEN" ]]; then
    echo "[runbook_env] Login failed. Check RUNBOOK_EMAIL and RUNBOOK_PASSWORD." >&2
    return 1
fi

export TOKEN RUNBOOK_URL RUNBOOK_EMAIL
echo "[runbook_env] Logged in as ${RUNBOOK_EMAIL} — token valid 30 days"

# ── Convenience functions ─────────────────────────────────────────────────────

# List incidents
runbook_incidents() {
    curl -s "${RUNBOOK_URL}/api/v1/incidents/" \
        -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
incs = json.load(sys.stdin)
if not incs:
    print('  No incidents found.')
    sys.exit(0)
print(f\"{'REF':<10} {'STATUS':<22} {'SEV':<5} {'TITLE'}\")
print('-' * 70)
for i in sorted(incs, key=lambda x: x.get('incident_number') or 0):
    ref  = f\"INC-{str(i.get('incident_number',0)).zfill(4)}\"
    stat = i.get('status','')
    sev  = i.get('severity','')
    ttl  = i.get('title','')[:40]
    print(f'{ref:<10} {stat:<22} {sev:<5} {ttl}')
"
}

# Show full AI report for an incident
runbook_report() {
    local inc_ref="${1:-}"
    if [[ -z "$inc_ref" ]]; then echo "Usage: runbook_report INC-0014"; return 1; fi
    local num="${inc_ref#INC-}"
    local inc_id
    inc_id=$(curl -s "${RUNBOOK_URL}/api/v1/incidents/" \
        -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
incs = json.load(sys.stdin)
num = int('${num}'.lstrip('0') or '0')
for i in incs:
    if i.get('incident_number') == num:
        print(i['id'])
        break
")
    if [[ -z "$inc_id" ]]; then echo "Incident $inc_ref not found."; return 1; fi

    curl -s "${RUNBOOK_URL}/api/v1/incidents/${inc_id}" \
        -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
inc = json.load(sys.stdin)
r   = inc.get('ai_report') or {}
print()
print(f\"INC-{str(inc.get('incident_number',0)).zfill(4)} — {inc['title']}\")
print(f\"Status    : {inc['status']}  |  Severity: {inc['severity']}\")
print(f\"Device    : {inc.get('affected_device','N/A')}  |  Protocol: {inc.get('affected_protocol','N/A')}\")
print()
if not r:
    print('No AI report yet. Run /diagnose first.')
    sys.exit(0)
print(f\"Confidence: {r.get('confidence', 0):.0%}  |  Urgency: {r.get('urgency','')}\")
print(f\"LLM       : {r.get('llm_provider','')}\")
print()
print('ROOT CAUSE:')
print(' ', r.get('root_cause',''))
print()
print('STEPS:')
for s in r.get('steps', []):
    print(' ', s)
print()
agents = r.get('orchestration', {}).get('agents_invoked', [])
if agents:
    print('AGENTS:', ', '.join(agents))
"
}

# Trigger diagnosis
runbook_diagnose() {
    local inc_ref="${1:-}"
    if [[ -z "$inc_ref" ]]; then echo "Usage: runbook_diagnose INC-0014"; return 1; fi
    local num="${inc_ref#INC-}"
    local inc_id
    inc_id=$(curl -s "${RUNBOOK_URL}/api/v1/incidents/" \
        -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
num = int('${num}'.lstrip('0') or '0')
for i in json.load(sys.stdin):
    if i.get('incident_number') == num:
        print(i['id']); break
")
    if [[ -z "$inc_id" ]]; then echo "Incident $inc_ref not found."; return 1; fi
    curl -s -X POST "${RUNBOOK_URL}/api/v1/incidents/${inc_id}/diagnose" \
        -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
}

# Show remediation plan
runbook_remediation() {
    local inc_ref="${1:-}"
    if [[ -z "$inc_ref" ]]; then
        echo "Usage: runbook_remediation INC-0014"
        echo "       python3 scripts/remediation_cli.py --incident INC-0014"
        return 1
    fi
    python3 scripts/remediation_cli.py \
        --incident "$inc_ref" \
        --url "$RUNBOOK_URL" \
        --email "$RUNBOOK_EMAIL" \
        --password "$RUNBOOK_PASSWORD"
}

echo "[runbook_env] Functions available:"
echo "  runbook_incidents          — list all incidents"
echo "  runbook_report INC-XXXX    — show AI diagnosis report"
echo "  runbook_diagnose INC-XXXX  — trigger AI diagnosis"
echo "  runbook_remediation INC-XXXX — interactive remediation approval"
