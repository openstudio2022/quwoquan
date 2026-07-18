#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

platform_base="${PLATFORM_OPS_BASE_URL:-http://127.0.0.1:18092}"
product_base="${PRODUCT_OPS_BASE_URL:-http://127.0.0.1:18091}"

check_json() {
  local url="$1"
  local label="$2"
  python3 - "$url" "$label" <<'PY'
import json
import time
import sys
import urllib.request

url, label = sys.argv[1:3]
last_error = None
for _ in range(40):
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        break
    except Exception as exc:  # noqa: BLE001
        last_error = exc
        time.sleep(0.5)
else:
    raise SystemExit(f"FAIL: {label} not ready: {last_error}")
if not payload:
    raise SystemExit(f"FAIL: {label} returned empty payload")
print(f"[smoke] OK: {label} -> {url}")
PY
}

check_json "$platform_base/healthz" "platform health"
check_json "$platform_base/control-plane/platform/topology/clusters" "platform clusters"
check_json "$platform_base/control-plane/platform/configs" "platform config keys"
check_json "$platform_base/control-plane/platform/configs/resolve?env=beta&cluster=beta-control-a&service=product-ops-service" "platform effective config"
check_json "$platform_base/control-plane/platform/configs/instances" "platform instance reports"
check_json "$product_base/healthz" "product health"
check_json "$product_base/control-plane/product/metrics/l1l4?env=beta" "product l1l4 metrics"
