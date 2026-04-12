#!/usr/bin/env bash
# 弱类型基线：dynamic / Object? 行数 + ASSISTANT_WEAK_TYPE 标签分布（不含 generated）。
# 用法：从仓库根或 quwoquan_app 下执行均可。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ASSISTANT_LIB="$APP_ROOT/lib/assistant"

count_dyn() {
  find "$1" -name '*.dart' ! -path '*/generated/*' -print0 2>/dev/null |
    xargs -0 grep -h '\bdynamic\b' 2>/dev/null | wc -l | tr -d ' '
}
count_object_q() {
  find "$1" -name '*.dart' ! -path '*/generated/*' -print0 2>/dev/null |
    xargs -0 grep -hE '\bObject\?' 2>/dev/null | wc -l | tr -d ' '
}
count_tag() {
  local tag="$2"
  find "$1" -name '*.dart' ! -path '*/generated/*' -print0 2>/dev/null |
    xargs -0 grep -hF "ASSISTANT_WEAK_TYPE: $tag" 2>/dev/null | wc -l | tr -d ' '
}

echo "== quwoquan_app lib/assistant (excluding **/generated) =="
echo -n "  dynamic lines: "; count_dyn "$ASSISTANT_LIB" || echo "0"
echo -n "  Object? lines: "; count_object_q "$ASSISTANT_LIB" || echo "0"
echo "  ASSISTANT_WEAK_TYPE tag lines:"
for t in JSON_BOUNDARY VENDOR_JSON EXTENSION_MAP LLM_RAW; do
  echo -n "    $t: "; count_tag "$ASSISTANT_LIB" "$t" || echo "0"
done

echo "== quwoquan_app lib/ui/assistant =="
UIA="$APP_ROOT/lib/ui/assistant"
echo -n "  dynamic lines: "; count_dyn "$UIA" || echo "0"
echo -n "  Object? lines: "; count_object_q "$UIA" || echo "0"
