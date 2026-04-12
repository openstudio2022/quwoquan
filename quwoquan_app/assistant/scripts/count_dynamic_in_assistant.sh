#!/usr/bin/env bash
# 可选度量：助手相关目录中弱类型命中（不含 generated）。
# 更完整标签统计见同目录 count_weak_types_in_assistant.sh。
# - dynamic：关键字行数
# - Object? / "Object " 形参：Codec/边界常见，单独计数便于趋势观察
# 不作为硬 CI 门禁；新增裸 dynamic 建议按 assistant_dynamic_typing_policy.md 加 ASSISTANT_WEAK_TYPE 注释。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
count_dyn() {
  local dir="$1"
  find "$dir" -name '*.dart' ! -path '*/generated/*' -print0 2>/dev/null |
    xargs -0 grep -h '\bdynamic\b' 2>/dev/null | wc -l | tr -d ' '
}
count_object_optional() {
  local dir="$1"
  find "$dir" -name '*.dart' ! -path '*/generated/*' -print0 2>/dev/null |
    xargs -0 grep -hE '\bObject\?' 2>/dev/null | wc -l | tr -d ' '
}
echo "== quwoquan_app: lib/assistant (excluding **/generated) =="
echo -n "  dynamic lines: "; count_dyn "$ROOT/lib/assistant" || echo "0"
echo -n "  Object? lines: "; count_object_optional "$ROOT/lib/assistant" || echo "0"
echo "== quwoquan_app: lib/ui/assistant =="
echo -n "  dynamic lines: "; count_dyn "$ROOT/lib/ui/assistant" || echo "0"
echo -n "  Object? lines: "; count_object_optional "$ROOT/lib/ui/assistant" || echo "0"
