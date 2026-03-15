#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:19191}"
TOKEN="${PERSONAL_ASSISTANT_GATEWAY_TOKEN:-}"
PROVIDER_ID="${2:-synthetic_provider}"

AUTH_HEADER=()
if [[ -n "$TOKEN" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${TOKEN}")
fi

echo "== alert routing config =="
curl -s "${BASE_URL}/v1/assistant/alerts/config" "${AUTH_HEADER[@]}"
echo

echo "== dispatch warning alert =="
curl -s -X POST "${BASE_URL}/v1/assistant/alerts/test" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "{
    \"providerId\": \"${PROVIDER_ID}\",
    \"severity\": \"warning\",
    \"message\": \"manual warning alert test\"
  }"
echo

echo "== dispatch critical alert =="
curl -s -X POST "${BASE_URL}/v1/assistant/alerts/test" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "{
    \"providerId\": \"${PROVIDER_ID}\",
    \"severity\": \"critical\",
    \"message\": \"manual critical alert test\"
  }"
echo

echo "== recent alerts =="
curl -s "${BASE_URL}/v1/assistant/alerts" "${AUTH_HEADER[@]}"
echo
