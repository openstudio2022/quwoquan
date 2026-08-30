"""deployment_candidate_manifest 包的共享 schema/正则/路径常量。"""

from __future__ import annotations

import re
from pathlib import Path

# 本文件位于包目录内，比原单文件多一层，因此取 parents[4] 才是仓库根。
ROOT = Path(__file__).resolve().parents[4]

CANDIDATE_MANIFEST_SCHEMA = "stackctl-deployment-candidate"
RUNTIME_CANDIDATE_TYPE = "runtime-full"
PROVIDER_RUNTIME_PACKAGE_SCHEMA = "stackctl-provider-runtime-package"
OBSERVABILITY_LOG_SINK_PACKAGE_SCHEMA = (
    "stackctl-observability-log-sink-package"
)
ENVIRONMENT_ARTIFACT_METADATA_PATH = (
    ROOT
    / "quwoquan_service/contracts/metadata/_shared/environment_artifact_identity.yaml"
)
ENVIRONMENT_ARTIFACT_SCHEMA_PATH = (
    ROOT
    / "quwoquan_service/contracts/metadata/_schemas/environment_artifact_identity.schema.json"
)
SPEC_REFS = (
    "AppRoot/JNY-002/SCN-005/UAT-003",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-001",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-002",
    "runtime/runtime-config/environment-ops-cli-and-skill/GWT-001",
    "runtime/deliver-deploy-prod-pipeline/SIT-001",
    "runtime/system-architecture-and-engineering-guide/SIT-003",
    "runtime/runtime-data-engineering/SIT-001",
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_RELEASE_LIFECYCLE_CLASSES = frozenset({"research", "commercial"})
_RELEASE_BINDING_FIELDS = frozenset(
    {
        "releaseId",
        "releaseDigest",
        "attestationRef",
        "attestationDigest",
        "releaseClass",
        "productLifecycleState",
    }
)
RELEASE_INPUT_CLASSIFICATIONS = frozenset(
    {"research_inputs", "commercial_inputs", "mixed_inputs"}
)
CANDIDATE_VALIDATION_PURPOSES = frozenset(
    {"self_verify", "currentness", "teardown"}
)
CONTRACT_GRAPH_PATH = ROOT / "quwoquan_service/generated/contract_graph.json"
LOG_SINK_ADAPTER_ID = "ext.obs.elasticsearch"
