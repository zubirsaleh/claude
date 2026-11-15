#!/usr/bin/env bash
# End-to-end SIM smoke test through the reverse proxy.
# Usage: TSCH_SITE_ADDRESS=":80" docker compose -f infra/docker/docker-compose.yml up -d --wait
#        infra/scripts/smoke-sim.sh [base_url]
set -euo pipefail
cd "$(dirname "$0")/../.."
B=${1:-http://localhost}
TOK=$(cat secrets/operator_token)
H=(-H "Authorization: Bearer $TOK" -H "Content-Type: application/json")
j() { python3 -c "import json,sys;d=json.load(sys.stdin);print($1)"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "health:    $(curl -s "$B/health")"
echo "docs:      HTTP $(code "$B/docs") (expect 404)"
echo "noauth:    HTTP $(code -X POST "$B/api/v1/orders/proposals" -H 'Content-Type: application/json' -d '{}') (expect 401)"

# Probe the current SIM entry with a deliberately oversized stop (rejected), then use entry - 10.
ENTRY=$(curl -s "${H[@]}" -X POST "$B/api/v1/orders/proposals" \
  -d '{"account_mode":"SIM","symbol":"XAUUSD","side":"BUY","volume":"0.01","sl":"1.00","reason":"smoke probe"}' | j 'd["est_entry"]')
SL=$(python3 -c "print(round(float('$ENTRY')-10,2))")
P="{\"account_mode\":\"SIM\",\"symbol\":\"XAUUSD\",\"side\":\"BUY\",\"volume\":\"0.01\",\"sl\":\"$SL\",\"reason\":\"smoke\"}"

O=$(curl -s "${H[@]}" -X POST "$B/api/v1/orders/proposals" -d "$P"); ID=$(echo "$O" | j 'd["id"]')
echo "propose:   $(echo "$O" | j 'd["state"], d["est_loss_at_stop"], d["est_risk_pct"]')"
echo "approve:   $(curl -s "${H[@]}" -X POST "$B/api/v1/orders/$ID/approve" | j 'd["state"]')"
echo "submit:    $(curl -s "${H[@]}" -X POST "$B/api/v1/orders/$ID/submit" | j 'd["state"], d["fill_price"]')"
echo "resubmit:  HTTP $(code "${H[@]}" -X POST "$B/api/v1/orders/$ID/submit") (expect 409)"
R=$(curl -s "${H[@]}" -X POST "$B/api/v1/orders/$ID/reconcile")
echo "reconcile: $(echo "$R" | j 'd["state"], d["outcome"]')"
PID=$(echo "$R" | j 'd["position_id"]')
echo "close:     $(curl -s "${H[@]}" -H "Idempotency-Key: smoke-close-$ID" -X POST "$B/api/v1/sim/positions/$PID/close" -d '{"confirm":true}')"
echo "fills:     $(curl -s "$B/api/v1/fills" | j '[(f["entry"], f["price"], f["profit"], f["commission"], f["source"]) for f in d]')"
curl -s "${H[@]}" -X PUT "$B/api/v1/risk/kill-switch" -d '{"engaged":true}' >/dev/null
echo "killswitch: $(curl -s "${H[@]}" -X POST "$B/api/v1/orders/proposals" -d "$P" | j 'd["state"], d["risk_reasons"][:1]')"
curl -s "${H[@]}" -X PUT "$B/api/v1/risk/kill-switch" -d '{"engaged":false}' >/dev/null
echo "audit:     $(curl -s "$B/api/v1/audit/verify")"
echo "web:       HTTP $(code "$B/")"
