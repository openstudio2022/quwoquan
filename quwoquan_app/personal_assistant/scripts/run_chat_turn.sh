#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:19191}"
TOKEN="${PERSONAL_ASSISTANT_GATEWAY_TOKEN:-}"
QUESTION="${2:-帮我搜索今天的财经热点并做简短总结}"

AUTH_HEADER=()
if [[ -n "$TOKEN" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${TOKEN}")
fi

curl -s -X POST "${BASE_URL}/v1/assistent/runs" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "{
    \"sessionId\": \"assistant\",
    \"channel\": \"app\",
    \"traceId\": \"script_$(date +%s)\",
    \"deviceProfile\": \"mobile\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"${QUESTION}\"}
    ]
  }"
echo
