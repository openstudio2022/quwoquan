# provider_conformance: {"adapterId":"ext.obs.postgres_telemetry_local","capabilityId":"runtime.log.sink","testLayer":"user_acceptance","typedPort":"ObservabilityLogSinkPort","contractRef":"quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.observability_log_sink"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/product-ops-service/ci/ext_obs_postgres_telemetry_local_provider_conformance.py"],"target":"ext-obs-postgres_telemetry_local-user-acceptance","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.obs.postgres_telemetry_local user_acceptance Provider suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-obs-postgres_telemetry_local-user-acceptance'
COMMAND = ('python3', 'quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py', '--target', 'test/user_acceptance/patrol/ops/event_ingestion_journey__user_acceptance_test.dart', '--platform', 'android')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
