#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "[gate] Step 1/2: flutter analyze"
flutter analyze \
  lib/assistant/assistant.dart \
  lib/assistant/api/assistant_api_gateway.dart \
  lib/assistant/application/assistant_providers.dart \
  lib/assistant/application/assistant_gateway.dart \
  lib/assistant/application/capability_gateway.dart \
  lib/assistant/application/assistant_edge_service.dart \
  lib/assistant/contracts/assistant_turn_contract.dart \
  lib/assistant/contracts/process_protocol.dart \
  lib/assistant/infrastructure/openclaw_bridge.dart \
  lib/assistant/orchestration/process_journal_bus.dart \
  lib/assistant/runtime/assistant_runtime.dart \
  lib/ui/chat/pages/chat_detail_page.dart \
  test/assistant/process_protocol_governance_test.dart \
  test/assistant/runtime_string_governance_test.dart \
  test/assistant/no_hardcoded_prompt_test.dart

echo "[gate] Step 2/2: flutter tests"
flutter test \
  test/assistant/assistant_turn_contract_roundtrip_test.dart \
  test/assistant/assistant_contract_models_test.dart \
  test/assistant/assistant_metadata_contract_split_test.dart \
  test/assistant/process_protocol_governance_test.dart \
  test/assistant/runtime_string_governance_test.dart \
  test/assistant/no_hardcoded_prompt_test.dart \
  test/assistant/runtime_enums_roundtrip_test.dart \
  test/assistant/query_task_contract_test.dart \
  test/assistant/llm_response_parser_test.dart \
  test/assistant/message_history_protocol_contract_test.dart \
  test/assistant/full_phase_pipeline_test.dart \
  test/assistant/phase_lifecycle_e2e_test.dart \
  test/assistant/new_tools_e2e_test.dart \
  test/ui/chat/widgets/chat_message_bubble_widget_test.dart

echo "[gate] PASS: runtime truth regression gate passed"
