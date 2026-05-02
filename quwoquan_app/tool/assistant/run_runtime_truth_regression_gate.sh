#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "[gate] Step 1/3: current marker scan"
python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path(".")
targets = [
    root / "lib",
    root / "assets" / "assistant",
    root / "assistant" / "docs",
    root / "test",
    root / "tool" / "assistant",
]
pattern = re.compile(
    r"\bagent_loop\b|CapabilityGateway|capability_gateway\.dart|"
    r"stack\.global_system|stack\.runtime_policy|stack\.recovery_policy|"
    r"stack\.global_policy|stack\.output_contract|\bthinkingText\b|"
    r"uiUsageStatsV1|processJournalV1|\buiAnswer\b|"
    r"process_journal_bus|process_event_consolidator|"
    r"trace_user_event_translator|ui_process_timeline_entry"
)

matches = []
for target in targets:
    if not target.exists():
        continue
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "run_runtime_truth_regression_gate.sh":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                matches.append(f"{path}:{idx}:{line.strip()}")

if matches:
    print("[gate][fatal] current assistant markers are still present:")
    for item in matches:
        print(item)
    sys.exit(11)

print("[gate] no current markers detected")
PY

echo "[gate] Step 2/3: flutter analyze"
flutter analyze \
  lib/assistant/assistant.dart \
  lib/assistant/api/assistant_api_gateway.dart \
  lib/assistant/application/assistant_providers.dart \
  lib/assistant/application/assistant_gateway.dart \
  lib/assistant/application/assistant_edge_service.dart \
  lib/assistant/application/local_assistant_entry.dart \
  lib/assistant/application/remote_assistant_entry.dart \
  lib/assistant/contracts/assistant_turn_contract.dart \
  lib/assistant/contracts/process_protocol.dart \
  lib/assistant/infrastructure/llm/llm_provider.dart \
  lib/assistant/infrastructure/openclaw_bridge.dart \
  lib/assistant/orchestration/execution_preparation_resolver.dart \
  lib/assistant/orchestration/pipelines/assistant_pipeline_engine.dart \
  lib/assistant/runtime/assistant_runtime.dart \
  lib/ui/chat/pages/chat_detail_page.dart \
  test/assistant/prompt_v2_e2e_test.dart \
  test/assistant/process_protocol_governance_test.dart \
  test/assistant/runtime_string_governance_test.dart \
  test/assistant/no_hardcoded_prompt_test.dart

echo "[gate] Step 3/3: flutter tests"
flutter test \
  test/assistant/assistant_turn_contract_roundtrip_test.dart \
  test/assistant/assistant_contract_models_test.dart \
  test/assistant/assistant_metadata_index_sanity_test.dart \
  test/assistant/log_completeness_contract_test.dart \
  test/assistant/process_protocol_governance_test.dart \
  test/assistant/prompt_v2_e2e_test.dart \
  test/assistant/runtime_string_governance_test.dart \
  test/assistant/no_hardcoded_prompt_test.dart \
  test/assistant/observability_completeness_test.dart \
  test/assistant/runtime_enums_roundtrip_test.dart \
  test/assistant/search_plan_contract_test.dart \
  test/assistant/llm_response_parser_test.dart \
  test/assistant/message_history_protocol_contract_test.dart \
  test/assistant/full_phase_pipeline_test.dart \
  test/assistant/phase_lifecycle_e2e_test.dart \
  test/assistant/new_tools_e2e_test.dart \
  test/ui/chat/widgets/chat_message_bubble_widget_test.dart

echo "[gate] PASS: runtime truth regression gate passed"
