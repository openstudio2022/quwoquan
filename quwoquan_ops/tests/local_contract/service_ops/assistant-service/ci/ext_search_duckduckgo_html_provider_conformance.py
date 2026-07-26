# provider_conformance: {"adapterId":"ext.search.duckduckgo_html","capabilityId":"assistant.public.search","testLayer":"local_contract","typedPort":"PublicSearchPort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_conversation/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.public_search"],"command":["python3","quwoquan_ops/tests/local_contract/service_ops/assistant-service/ci/ext_search_duckduckgo_html_provider_conformance.py"],"target":"ext-search-duckduckgo_html-local-contract","networkBoundary":"offline_harness"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.search.duckduckgo_html offline native conformance suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-search-duckduckgo_html-local-contract'
COMMAND = ('go', '-C', 'quwoquan_service', 'test', './services/assistant-service/internal/...', './services/assistant-service/tests/local_contract/...', '-count=1')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
