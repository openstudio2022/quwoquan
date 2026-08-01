# provider_conformance: {"adapterId":"ext.finance.yahoo_chart","capabilityId":"assistant.finance.quote","testLayer":"user_acceptance","typedPort":"FinanceQuotePort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.finance_quote"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/ci/ext_finance_yahoo_chart_provider_conformance.py"],"target":"ext-finance-yahoo_chart-user-acceptance","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
"""Execute the ext.finance.yahoo_chart production-Remote user journey."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-finance-yahoo_chart-user-acceptance'
COMMAND = ('python3', 'quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py', '--target', 'test/user_acceptance/patrol/assistant/finance_provider__user_acceptance_test.dart', '--platform', 'android')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
