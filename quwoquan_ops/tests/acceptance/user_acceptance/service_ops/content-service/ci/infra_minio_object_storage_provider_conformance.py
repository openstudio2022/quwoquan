# provider_conformance: {"adapterId":"infra.minio.object_storage","capabilityId":"runtime.object.storage","testLayer":"user_acceptance","typedPort":"ObjectStoragePort","contractRef":"quwoquan_service/services/content-service/contracts/content/post/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.object_storage"],"command":["python3","quwoquan_ops/tests/acceptance/user_acceptance/service_ops/content-service/ci/infra_minio_object_storage_provider_conformance.py"],"target":"infra-minio-object_storage-user-acceptance","networkBoundary":"user_journey"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
"""Execute the infra.minio.object_storage production-Remote user journey."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'infra-minio-object_storage-user-acceptance'
COMMAND = ('python3', 'quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py', '--target', 'test/user_acceptance/patrol/content/media_publication_remote__user_acceptance_test.dart', '--platform', 'android')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
