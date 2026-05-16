#!/usr/bin/env bash
# PA Core Tests — 按执行依赖分桶运行
#
# 桶 A: flutter test — 协议契约级，无网络依赖，最先执行，失败即退（最快发现根因）
# 桶 B: flutter test — 引擎集成，依赖完整 Flutter 工具链（分钟级）
# 桶 C: flutter test — UI Widget 契约层（widget 测试但无网络依赖）
#
# 注：所有桶均使用 flutter test 执行（dart test 在此项目有 analyzer 版本冲突）
#
# 用法：
#   bash scripts/run_pa_core_tests.sh          # 跑全部桶（A+B+C）
#   bash scripts/run_pa_core_tests.sh --bucket-a  # 只跑桶 A（最快、最稳定）
#
# Gate 策略：
#   - 桶 A 失败 → 立即退出（基础协议契约）
#   - 桶 B 失败 → 立即退出（引擎集成契约）
#   - 桶 C 失败 → 立即退出（UI 消息构建契约）
#
# 自主修复指引（编程助手用）：
#   ...tool_observation...          → react_runtime.dart / llm_provider.dart
#   ...history_contamination...     → agent_loop.dart / session_manager.dart / chat_detail_page.dart
#   ...assistant_answer_protocol... → assistant_repository / stream protocol / transcript payload
#   ...assistant_message_history... → local timeline persistence / transcript rendering
#   ...stream_controller...         → PersonalAssistantStreamController / resolver / provider
#   ...assistant_skill_center...    → skill center page / consent management / repository projection

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$ROOT/quwoquan_app"
cd "$APP_DIR"

BUCKET_A_ONLY=false
if [[ "${1:-}" == "--bucket-a" ]]; then
  BUCKET_A_ONLY=true
fi

# ══════════════════════════════════════════════════════════════════════════════
# 桶 A: dart test — 纯 Dart VM，无 flutter shell（最快、最稳定）
# 覆盖：A3/A4/A8 协议契约（回答协议、消息时间轴、只读投影）
# ══════════════════════════════════════════════════════════════════════════════
BUCKET_A_TESTS=(
  "test/common/assistant/protocol/assistant_answer_protocol_leak_regression_test.dart"
  "test/ui/assistant/contract/assistant_message_history_contract_test.dart"
  "test/ui/assistant/assistant_context_scope_read_view_test.dart"
  "test/ui/assistant/assistant_structured_run_response_read_view_test.dart"
)

echo "[pa-core] ── Bucket A: flutter test (pure VM, no network) ─────────────────"
for t in "${BUCKET_A_TESTS[@]}"; do
  echo "[pa-core] -> $t"
  flutter test "$t" --no-pub -r compact 2>&1 || {
    echo "[pa-core] FAIL: $t" >&2
    exit 1
  }
done
echo "[pa-core] Bucket A: OK"

if [[ "$BUCKET_A_ONLY" == "true" ]]; then
  echo "[pa-core] --bucket-a 模式，跳过桶 B/C"
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# 桶 B: flutter test — 引擎集成测试（需要 flutter tester shell）
# 覆盖：A3/A8/A9 状态编排、消息解析与 Provider 投影
# ══════════════════════════════════════════════════════════════════════════════
BUCKET_B_TESTS=(
  "test/ui/assistant/personal_assistant_stream_controller_test.dart"
  "test/ui/assistant/assistant_turn_message_resolver_transcript_row_test.dart"
  "test/ui/assistant/personal_content_access_provider_test.dart"
)

echo "[pa-core] ── Bucket B: flutter test (engine integration) ─────────────────"
for t in "${BUCKET_B_TESTS[@]}"; do
  echo "[pa-core] -> $t"
  flutter test "$t" --no-pub -r compact 2>&1 || {
    echo "[pa-core] FAIL: $t" >&2
    exit 1
  }
done
echo "[pa-core] Bucket B: OK"

# ══════════════════════════════════════════════════════════════════════════════
# 桶 C: flutter test — UI 契约层（widget 级别但无网络依赖）
# 覆盖：A3/A10 页面与消息 UI 契约
# ══════════════════════════════════════════════════════════════════════════════
BUCKET_C_TESTS=(
  "test/ui/assistant/assistant_transcript_bubble_envelope_test.dart"
  "test/ui/assistant/assistant_management_page_consent_test.dart"
  "test/ui/assistant/pages/assistant_skill_center_page_widget_test.dart"
)

echo "[pa-core] ── Bucket C: flutter test (UI contract) ────────────────────────"
for t in "${BUCKET_C_TESTS[@]}"; do
  echo "[pa-core] -> $t"
  flutter test "$t" --no-pub -r compact 2>&1 || {
    echo "[pa-core] FAIL (flutter test): $t" >&2
    exit 1
  }
done
echo "[pa-core] Bucket C: OK"

echo "[pa-core] ── All PA Core tests passed ──────────────────────────────────"
