# provider_conformance: {"adapterId":"ext.oss.s3_compatible","capabilityId":"runtime.object.storage","testLayer":"api_integration","typedPort":"ObjectStoragePort","contractRef":"quwoquan_service/services/content-service/contracts/content/post/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.object_storage"],"command":["python3","quwoquan_ops/tests/acceptance/api_integration/service_ops/content-service/ci/ext_oss_s3_compatible_provider_conformance.py"],"target":"ext-oss-s3_compatible-api-integration","networkBoundary":"remote_protocol"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.oss.s3_compatible native protocol-integration suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-oss-s3_compatible-api-integration'
COMMAND = ('go', '-C', 'quwoquan_service', 'test', './services/content-service/tests/api_integration/content/post/...', '-count=1')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
