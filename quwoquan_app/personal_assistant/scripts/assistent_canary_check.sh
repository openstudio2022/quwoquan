#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:19191}"
TOKEN="${PERSONAL_ASSISTANT_GATEWAY_TOKEN:-}"
QUESTION="${2:-请给出杭州明日天气与出行建议}"

AUTH_HEADER=()
if [[ -n "$TOKEN" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${TOKEN}")
fi

echo "== adapters =="
curl -s "${BASE_URL}/v1/assistent/adapters" "${AUTH_HEADER[@]}"
echo

echo "== providers =="
curl -s "${BASE_URL}/v1/assistent/providers" "${AUTH_HEADER[@]}"
echo

echo "== run =="
curl -s -X POST "${BASE_URL}/v1/assistent/runs" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "{
    \"sessionId\": \"assistent-canary\",
    \"channel\": \"app\",
    \"traceId\": \"canary_$(date +%s)\",
    \"deviceProfile\": \"mobile\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"${QUESTION}\"}
    ]
  }"
echo

echo "== alerts =="
curl -s "${BASE_URL}/v1/assistent/alerts" "${AUTH_HEADER[@]}"
echo

echo "== optional recover sample (replace provider id) =="
echo "curl -s -X POST \"${BASE_URL}/v1/assistent/providers/local_heuristic/recover\" ${AUTH_HEADER[*]}"
echo

echo "== costs =="
curl -s "${BASE_URL}/v1/assistent/costs" "${AUTH_HEADER[@]}"
echo

