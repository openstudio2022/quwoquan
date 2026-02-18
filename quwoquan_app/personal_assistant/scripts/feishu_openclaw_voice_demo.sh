#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:19191}"
TOKEN="${PERSONAL_ASSISTANT_GATEWAY_TOKEN:-}"
VOICE_TEXT="${2:-帮我查一下今日杭州天气和出行建议}"
TRACE_ID="feishu_$(date +%s)"

AUTH_HEADER=()
if [[ -n "$TOKEN" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${TOKEN}")
fi

echo "== Step1: Feishu webhook -> adapter ingress =="
curl -s -X POST "${BASE_URL}/v1/assistent/channels/feishu" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "{
    \"text\": \"${VOICE_TEXT}\"
  }"
echo

echo "== Step2: OpenClaw style stream run with trace =="
curl -N -X POST "${BASE_URL}/v1/assistent/runs/stream" \
  -H "Content-Type: application/json" \
  "${AUTH_HEADER[@]}" \
  -d "{
    \"sessionId\": \"feishu-openclaw-demo\",
    \"channel\": \"openclaw\",
    \"traceId\": \"${TRACE_ID}\",
    \"deviceProfile\": \"pc\",
    \"messages\": [
      { \"role\": \"user\", \"content\": \"${VOICE_TEXT}\" }
    ]
  }"
echo

echo "== Step3: Query session history =="
curl -s -X GET "${BASE_URL}/v1/assistent/sessions" "${AUTH_HEADER[@]}"
echo
