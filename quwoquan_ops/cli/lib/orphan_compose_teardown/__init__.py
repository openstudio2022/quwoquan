"""Candidate-independent, exact-resource recovery for orphaned local Compose stacks.

This module deliberately does not accept a Compose project from argv. The
eligible project is either the exact target-bound formal release identity or
the target's one canonical mutable test-live identity, bound by a receipt or
attestation or uniquely discovered from Docker labels. A read-only
inventory is sealed once, expires quickly, and must match a complete
second inventory before any exact resource ID is removed.

原单文件 ``orphan_compose_teardown.py`` 拆分为同名包；本 ``__init__`` re-export
全部公开与被测私有符号，``stackctl`` 的模块属性访问与测试的
``from quwoquan_ops.cli.lib import orphan_compose_teardown`` 用法保持不变。
"""

from __future__ import annotations

from .constants import (  # noqa: F401
    ATTESTATION_TTL_SECONDS,
    CONSUMPTION_SCHEMA,
    CONVERGENCE_SCHEMA,
    JOURNAL_SCHEMA,
    LOCAL_TARGETS,
    SCHEMA,
    STEP_SCHEMA,
    OrphanComposeTeardownError,
    _DIGEST,
    _SAFE_LABEL,
    _canonical_bytes,
    _digest,
    _normalize_published_endpoints,
    _timestamp,
    _utc_text,
    canonical_project,
    canonical_project_kind,
    mutable_test_live_project,
    require_canonical_project,
)
from .inventory import (  # noqa: F401
    _canonical_mounts,
    _container_descriptor,
    _labels,
    _list_ids,
    _network_descriptor,
    _published_endpoints,
    _run_json,
    _volume_descriptor,
    discover_exact_project,
    sample_snapshot,
)
from .attestation import (  # noqa: F401
    _safe_attestation_path,
    assert_snapshot_unchanged,
    exact_removal_commands,
    load_attestation,
    seal_attestation,
    validate_attestation,
    write_attestation_create_once,
)
from .receipts import (  # noqa: F401
    _write_create_once,
    assert_not_consumed,
    assert_post_teardown_state,
    complete_execution_step_receipts,
    load_partial_consumption_for_convergence,
    validate_execution_evidence_for_convergence,
    validate_execution_journal_for_recovery,
    write_consumption_create_once,
    write_convergence_create_once,
    write_execution_journal_create_once,
    write_step_receipt_create_once,
)
