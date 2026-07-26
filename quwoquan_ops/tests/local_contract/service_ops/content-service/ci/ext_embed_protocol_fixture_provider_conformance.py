# provider_conformance: {"adapterId":"ext.embed.protocol_fixture","capabilityId":"content.embedding.generation","testLayer":"local_contract","typedPort":"EmbeddingGenerationPort","contractRef":"quwoquan_service/services/content-service/contracts/content/post/operations.yaml","assertionIds":["provider.auth","provider.callback_ordering","provider.idempotency","provider.network_dns","provider.observability","provider.redaction","provider.retry","provider.success","provider.throttle","provider.timeout","provider.validation","provider.embedding_generation"],"command":["python3","quwoquan_ops/tests/local_contract/service_ops/content-service/ci/ext_embed_protocol_fixture_provider_conformance.py"],"target":"ext-embed-protocol_fixture-local-contract","networkBoundary":"offline_harness"}
# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
"""Execute the ext.embed.protocol_fixture offline native conformance suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.native_case_result import run_native_harness

RESULT_PATH_ENV = "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"
TARGET = 'ext-embed-protocol_fixture-local-contract'
COMMAND = ('go', '-C', 'quwoquan_service', 'test', './services/content-service/internal/content/post/...', './services/content-service/tests/local_contract/content/post/...', '-count=1')

if __name__ == "__main__":
    raise SystemExit(run_native_harness(command=COMMAND, target=TARGET))
