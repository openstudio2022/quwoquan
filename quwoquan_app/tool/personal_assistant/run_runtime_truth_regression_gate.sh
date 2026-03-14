#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "[gate] Step 1/2: flutter analyze"
flutter analyze \
  lib/personal_assistant/contracts/assistant_turn_contract.dart \
  lib/personal_assistant/contracts/run_artifacts.dart \
  lib/personal_assistant/contracts/planner_contracts.dart \
  lib/personal_assistant/contracts/process_protocol.dart \
  lib/personal_assistant/protocol/run_response.dart \
  lib/personal_assistant/connectors/openclaw_bridge.dart \
  lib/personal_assistant/app/assistant_http_gateway.dart \
  lib/personal_assistant/app/capability_gateway.dart \
  lib/personal_assistant/engine/conversation_state_kernel.dart \
  lib/personal_assistant/engine/process_journal_bus.dart \
  lib/personal_assistant/engine/agent_loop.dart \
  lib/ui/chat/pages/chat_detail_page.dart \
  test/personal_assistant/process_protocol_governance_test.dart

echo "[gate] Step 2/2: flutter tests"
flutter test \
  test/personal_assistant/assistant_turn_contract_roundtrip_test.dart \
  test/personal_assistant/assistant_contract_models_test.dart \
  test/personal_assistant/assistant_metadata_contract_split_test.dart \
  test/personal_assistant/process_protocol_governance_test.dart \
  test/personal_assistant/runtime_enums_roundtrip_test.dart \
  test/personal_assistant/query_task_contract_test.dart \
  test/personal_assistant/llm_response_parser_test.dart \
  test/personal_assistant/message_history_protocol_contract_test.dart \
  test/personal_assistant/full_phase_pipeline_test.dart \
  test/personal_assistant/phase_lifecycle_e2e_test.dart \
  test/personal_assistant/new_tools_e2e_test.dart \
  test/ui/chat/widgets/chat_message_bubble_widget_test.dart

echo "[gate] PASS: runtime truth regression gate passed"
