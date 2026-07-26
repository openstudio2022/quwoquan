# provider_conformance: {"adapterId":"ext.obs.aliyun_sls","capabilityId":"runtime.log.sink","testLayer":"local_contract","typedPort":"ObservabilityLogSinkPort","contractRef":"quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.observability_log_sink"],"command":["python3","quwoquan_ops/tests/local_contract/service_ops/product-ops-service/ci/ext_obs_aliyun_sls_provider_conformance.py"],"target":"ext-obs-aliyun_sls-local-contract","networkBoundary":"offline_harness"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.obs.aliyun_sls offline native conformance suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-obs-aliyun_sls-local-contract'
COMMAND = ('go', '-C', 'quwoquan_service', 'test', './services/product-ops-service/internal/product_ops/event_record/...', './services/product-ops-service/tests/local_contract/product_ops/event_record/...', '-count=1')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
