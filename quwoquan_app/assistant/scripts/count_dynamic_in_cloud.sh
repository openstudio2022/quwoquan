#!/usr/bin/env bash
# 可选度量：云客户端手写目录中弱类型命中（不含 generated），与 count_dynamic_in_assistant.sh 并列趋势观察。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
count_dyn() {
  local dir="$1"
  find "$dir" -name '*.dart' ! -path '*/generated/*' ! -path '*/runtime/generated/*' -print0 2>/dev/null |
    xargs -0 grep -h '\bdynamic\b' 2>/dev/null | wc -l | tr -d ' '
}
count_object_optional() {
  local dir="$1"
  find "$dir" -name '*.dart' ! -path '*/generated/*' ! -path '*/runtime/generated/*' -print0 2>/dev/null |
    xargs -0 grep -hE '\bObject\?' 2>/dev/null | wc -l | tr -d ' '
}
echo "== quwoquan_app: lib/cloud (excluding **/generated, **/runtime/generated) =="
echo -n "  dynamic lines: "; count_dyn "$ROOT/lib/cloud" || echo "0"
echo -n "  Object? lines: "; count_object_optional "$ROOT/lib/cloud" || echo "0"
