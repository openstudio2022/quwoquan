"""travel-to-gathering 迁移控制面实现包。

实现按职责单轨切分为 constants / codec / target_contract / snapshots /
contract_validation / mapping_support / mapping / parity / evidence /
receipts / control_receipts / cli；稳定入口模块 ``control_plane`` 从这里
re-export 原有的全部顶层符号（含测试消费的私有 ``_`` 符号），对既有消费者
（``stackctl migration`` 与 local_contract 测试）保持零漂移。
"""

from __future__ import annotations

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.cli import (
    _ensure_output_path,
    _report_dir,
    _required_cli_path,
    command,
    execute,
    register_parser,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _file_digest,
    _identity_digest,
    _load_object,
    _parse_timestamp,
    _require_digest,
    _require_nonblank,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    CANONICAL_TARGET_OBJECT_IDS,
    COMMAND_NAME,
    CONTROL_PHASES,
    CROSSWALK_PATH,
    DIGEST_RE,
    DISPOSITIONS,
    EMAIL_RE,
    ENVIRONMENTS,
    EVIDENCE_PHASES,
    HEX_DIGEST_RE,
    IDENTITY_KEY_RE,
    MIGRATION_ID,
    OPERATIONAL_EVIDENCE_SCHEMA,
    OPERATIONAL_EVIDENCE_TYPES,
    PHASES,
    PHONE_RE,
    RECEIPT_SCHEMA,
    REQUIRED_TARGET_OPERATION_IDS,
    ROLLBACK_MODES,
    ROOT,
    SAFE_WRITE_PLANES,
    SENSITIVE_KEY_RE,
    SOURCE_OBJECT_TYPES,
    SOURCE_SNAPSHOT_SCHEMA,
    SOURCE_STATUS_VALUES,
    TARGET_CONTRACT_BINDINGS,
    TARGET_CONTRACT_GRAPH,
    TARGET_GENERATED_MODELS,
    TARGET_OWNER_CONTRACT_FILENAMES,
    TARGET_SNAPSHOT_SCHEMA,
    TARGET_WRITE_SERVICES,
    TIMEZONE_RE,
    MappingResult,
    MigrationControlError,
    TargetContractBinding,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.contract_validation import (
    _constraints,
    _validate_contract_document,
    _validate_field_value,
    _validate_scalar_type,
    validate_gathering_document,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.control_receipts import (
    _control_receipt_base,
    build_cutover_receipt,
    build_rollback_receipt,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.evidence import (
    _evidence_ref,
    _load_operational_evidence,
    _validate_control_write_set,
    _validate_external_evidence_write_set,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.mapping import (
    build_mapping,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.mapping_support import (
    _binding_trip_id,
    _canonical_object_ref,
    _dedupe_blockers,
    _duration_minutes,
    _index_objects,
    _map_lifecycle_status,
    _map_membership_closed_reason,
    _map_plan_item,
    _mapping_record,
    _new_conflicts,
    _record_conflict,
    _safe_blocker,
    _target_plan_id,
    _target_revision_id,
    _trip_binding_issues,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.parity import (
    _dimension_projection,
    _disposition_summary,
    build_parity,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.receipts import (
    _assert_receipt_chain,
    _availability_sections,
    _load_migration_receipt,
    _seal_receipt,
    build_receipt,
    validate_receipt,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.snapshots import (
    _count_references,
    _pii_redaction_report,
    _snapshot_digest,
    _source_object_id,
    _status_key,
    build_inventory,
    load_source_snapshot,
    load_target_snapshot,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.target_contract import (
    _assert_generated_model_matches_fields,
    resolve_target_contract,
)

__all__ = [
    "COMMAND_NAME",
    "DISPOSITIONS",
    "ENVIRONMENTS",
    "MIGRATION_ID",
    "SOURCE_OBJECT_TYPES",
    "SOURCE_SNAPSHOT_SCHEMA",
    "TARGET_SNAPSHOT_SCHEMA",
    "MigrationControlError",
    "TargetContractBinding",
    "build_cutover_receipt",
    "build_inventory",
    "build_mapping",
    "build_parity",
    "build_receipt",
    "build_rollback_receipt",
    "canonical_digest",
    "command",
    "execute",
    "load_source_snapshot",
    "load_target_snapshot",
    "register_parser",
    "resolve_target_contract",
    "validate_gathering_document",
    "validate_receipt",
]
