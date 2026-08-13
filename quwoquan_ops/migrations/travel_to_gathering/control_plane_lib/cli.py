"""stackctl migration 子命令的 argparse 注册与执行编排。

内容逐字来自原 ``control_plane.py``；唯一差异是 ``execute`` 在函数体内经稳定
入口模块 ``control_plane`` 延迟解析 ``resolve_target_contract``，保持既有测试
对 ``control_plane.resolve_target_contract`` 的 monkeypatch 语义。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import artifact_run_dir, relpath, write_json
from quwoquan_ops.cli.lib.output_paths import output_root

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _require_digest,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    ENVIRONMENTS,
    EVIDENCE_PHASES,
    MIGRATION_ID,
    PHASES,
    RECEIPT_SCHEMA,
    ROLLBACK_MODES,
    ROOT,
    MigrationControlError,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.control_receipts import (
    build_cutover_receipt,
    build_rollback_receipt,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.evidence import (
    _load_operational_evidence,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.mapping import (
    build_mapping,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.receipts import (
    _assert_receipt_chain,
    _load_migration_receipt,
    build_receipt,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.snapshots import (
    load_source_snapshot,
    load_target_snapshot,
)


def _ensure_output_path(path: Path) -> Path:
    root = output_root().expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MigrationControlError(
            "OUTPUT_PATH_FORBIDDEN",
            "migration receipts may only be written under QWQ_OUTPUT_ROOT",
        ) from exc
    return resolved


def _report_dir(args: argparse.Namespace) -> Path:
    explicit = str(getattr(args, "report_dir", "") or "").strip()
    if explicit:
        return _ensure_output_path(Path(explicit))
    generated = artifact_run_dir(
        str(args.env),
        f"migration-{MIGRATION_ID}-{args.phase}",
        target="control-plane",
    )
    return _ensure_output_path(generated)


def _required_cli_path(
    args: argparse.Namespace,
    attribute: str,
    flag: str,
) -> Path:
    value = str(getattr(args, attribute, "") or "").strip()
    if not value:
        raise MigrationControlError(
            "REQUIRED_RECEIPT_MISSING",
            f"{flag} is required",
        )
    return Path(value)


def execute(
    args: argparse.Namespace,
    *,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    # 运行时经稳定入口模块查找 resolve_target_contract，保持既有测试对
    # control_plane.resolve_target_contract 的 monkeypatch 语义不变。
    from quwoquan_ops.migrations.travel_to_gathering.control_plane import (
        resolve_target_contract,
    )

    phase = str(args.phase)
    environment = str(args.env)
    report_dir: Path | None = None
    try:
        report_dir = _report_dir(args)
        if environment == "prod" and phase == "dry-run":
            raise MigrationControlError(
                "PROD_PHASE_FORBIDDEN",
                "prod permits read-only inventory/parity only; dry-run is GATE_BLOCK",
            )
        if phase in EVIDENCE_PHASES:
            source_snapshot_path = str(
                getattr(args, "source_snapshot", "") or ""
            ).strip()
            if not source_snapshot_path:
                raise MigrationControlError(
                    "SOURCE_SNAPSHOT_REQUIRED",
                    "--source-snapshot is required for inventory/dry-run/parity",
                )
            target_contract = resolve_target_contract(repository_root)
            snapshot = load_source_snapshot(
                Path(source_snapshot_path),
                environment=environment,
                target_contract_digest=target_contract.digest,
            )
            mapping = build_mapping(snapshot, target_contract)
            target_snapshot: dict[str, Any] | None = None
            if phase == "parity":
                target_snapshot_path = str(
                    getattr(args, "target_snapshot", "") or ""
                ).strip()
                if not target_snapshot_path:
                    raise MigrationControlError(
                        "TARGET_SNAPSHOT_REQUIRED",
                        "--target-snapshot is required for parity",
                    )
                target_snapshot = load_target_snapshot(
                    Path(target_snapshot_path),
                    environment=environment,
                    target_contract_digest=target_contract.digest,
                )
            receipt = build_receipt(
                environment=environment,
                phase=phase,
                snapshot=snapshot,
                target_contract=target_contract,
                mapping=mapping,
                target_snapshot=target_snapshot,
            )
        elif phase == "cutover":
            target_contract = resolve_target_contract(repository_root)
            inventory_receipt = _load_migration_receipt(
                _required_cli_path(
                    args,
                    "inventory_receipt",
                    "--inventory-receipt",
                ),
                environment=environment,
                phase="inventory",
            )
            parity_receipt = _load_migration_receipt(
                _required_cli_path(args, "parity_receipt", "--parity-receipt"),
                environment=environment,
                phase="parity",
            )
            _assert_receipt_chain(inventory_receipt, parity_receipt)
            common_digests = {
                "inventoryReceiptDigest": inventory_receipt["receiptDigest"],
                "parityReceiptDigest": parity_receipt["receiptDigest"],
                "sourceSnapshotDigest": parity_receipt["source"]["snapshotDigest"],
                "targetContractDigest": target_contract.digest,
                "crosswalkDigest": parity_receipt["crosswalkDigest"],
                "mappingDigest": parity_receipt["mapping"][
                    "targetDocumentDigest"
                ],
            }
            target_backup = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "target_backup_receipt",
                    "--target-backup-receipt",
                ),
                environment=environment,
                evidence_type="target_backup",
                expected_digests=common_digests,
                target_contract=target_contract,
            )
            source_freeze = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "source_freeze_receipt",
                    "--source-freeze-receipt",
                ),
                environment=environment,
                evidence_type="source_write_freeze",
                expected_digests=common_digests,
                target_contract=target_contract,
            )
            target_command = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "target_command_receipt",
                    "--target-command-receipt",
                ),
                environment=environment,
                evidence_type="target_command_import",
                expected_digests={
                    **common_digests,
                    "targetBackupEvidenceDigest": target_backup["evidenceDigest"],
                    "sourceFreezeEvidenceDigest": source_freeze["evidenceDigest"],
                },
                target_contract=target_contract,
            )
            _require_digest(
                target_command["subjectDigests"].get(
                    "protectedWriteApprovalDigest"
                ),
                label=(
                    "target_command_import.subjectDigests."
                    "protectedWriteApprovalDigest"
                ),
            )
            config_candidate_digest = _require_digest(
                getattr(args, "config_candidate_digest", ""),
                label="--config-candidate-digest",
            )
            planned_write_set = [
                {
                    "stepId": "cutover.activate-target-only-config",
                    "plane": "target_config",
                    "service": "circle-service",
                    "operation": "activate_target_only_candidate",
                    "candidateDigest": config_candidate_digest,
                    "executionMode": "external_approval_only",
                }
            ]
            planned_write_set_digest = canonical_digest(planned_write_set)
            approval_path = str(
                getattr(args, "approval_receipt", "") or ""
            ).strip()
            approval: dict[str, Any] | None = None
            if approval_path:
                approval = _load_operational_evidence(
                    Path(approval_path),
                    environment=environment,
                    evidence_type="protected_environment_approval",
                    expected_digests={
                        **common_digests,
                        "targetCommandEvidenceDigest": target_command[
                            "evidenceDigest"
                        ],
                        "configCandidateDigest": config_candidate_digest,
                        "writeSetDigest": planned_write_set_digest,
                    },
                    target_contract=target_contract,
                )
            activation_path = str(
                getattr(args, "config_activation_receipt", "") or ""
            ).strip()
            activation: dict[str, Any] | None = None
            if activation_path:
                if approval is None:
                    raise MigrationControlError(
                        "PROTECTED_ENVIRONMENT_APPROVAL_REQUIRED",
                        "config activation evidence requires prior approval evidence",
                    )
                activation = _load_operational_evidence(
                    Path(activation_path),
                    environment=environment,
                    evidence_type="target_config_activation",
                    expected_digests={
                        **common_digests,
                        "configCandidateDigest": config_candidate_digest,
                        "plannedWriteSetDigest": planned_write_set_digest,
                        "approvalEvidenceDigest": approval["evidenceDigest"],
                    },
                    target_contract=target_contract,
                )
            receipt = build_cutover_receipt(
                environment=environment,
                inventory_receipt=inventory_receipt,
                parity_receipt=parity_receipt,
                target_contract=target_contract,
                target_backup_evidence=target_backup,
                source_freeze_evidence=source_freeze,
                target_command_evidence=target_command,
                config_candidate_digest=config_candidate_digest,
                approval_evidence=approval,
                activation_evidence=activation,
            )
        elif phase == "rollback":
            target_contract = resolve_target_contract(repository_root)
            cutover_receipt = _load_migration_receipt(
                _required_cli_path(args, "cutover_receipt", "--cutover-receipt"),
                environment=environment,
                phase="cutover",
            )
            post_restore_parity = _load_migration_receipt(
                _required_cli_path(
                    args,
                    "post_restore_parity_receipt",
                    "--post-restore-parity-receipt",
                ),
                environment=environment,
                phase="parity",
            )
            rollback_mode = str(getattr(args, "rollback_mode", "") or "")
            if rollback_mode not in ROLLBACK_MODES:
                raise MigrationControlError(
                    "ROLLBACK_MODE_INVALID",
                    "--rollback-mode is required for rollback",
                )
            rollback_candidate_digest = _require_digest(
                getattr(args, "rollback_candidate_digest", ""),
                label="--rollback-candidate-digest",
            )
            planned_plane = (
                "target_config"
                if rollback_mode == "target_application_config"
                else "target_snapshot"
            )
            planned_operation = (
                "restore_target_application_config"
                if rollback_mode == "target_application_config"
                else "restore_target_snapshot"
            )
            planned_write_set_digest = canonical_digest(
                [
                    {
                        "stepId": f"rollback.{rollback_mode}",
                        "plane": planned_plane,
                        "service": "circle-service",
                        "operation": planned_operation,
                        "candidateDigest": rollback_candidate_digest,
                        "executionMode": "external_approval_only",
                    }
                ]
            )
            rollback_digests = {
                "cutoverReceiptDigest": cutover_receipt["receiptDigest"],
                "targetContractDigest": target_contract.digest,
                "crosswalkDigest": cutover_receipt["crosswalkDigest"],
                "sourceSnapshotDigest": cutover_receipt["source"][
                    "snapshotDigest"
                ],
                "rollbackCandidateDigest": rollback_candidate_digest,
                "plannedWriteSetDigest": planned_write_set_digest,
            }
            approval = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "approval_receipt",
                    "--approval-receipt",
                ),
                environment=environment,
                evidence_type="protected_environment_approval",
                expected_digests=rollback_digests,
                target_contract=target_contract,
            )
            restore = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "target_restore_receipt",
                    "--target-restore-receipt",
                ),
                environment=environment,
                evidence_type="target_restore",
                expected_digests={
                    **rollback_digests,
                    "approvalEvidenceDigest": approval["evidenceDigest"],
                    "restoredTargetSnapshotDigest": post_restore_parity[
                        "target"
                    ]["snapshotDigest"],
                },
                target_contract=target_contract,
            )
            restore_planes = {
                str(value.get("plane") or "")
                for value in restore["writeSet"]
                if isinstance(value, dict)
            }
            if restore_planes != {planned_plane}:
                raise MigrationControlError(
                    "ROLLBACK_WRITE_SET_MISMATCH",
                    "target restore evidence does not match rollback mode",
                )
            receipt = build_rollback_receipt(
                cutover_receipt=cutover_receipt,
                post_restore_parity_receipt=post_restore_parity,
                target_contract=target_contract,
                rollback_mode=rollback_mode,
                rollback_candidate_digest=rollback_candidate_digest,
                approval_evidence=approval,
                restore_evidence=restore,
            )
        else:
            raise MigrationControlError(
                "MIGRATION_PHASE_INVALID",
                f"unsupported migration phase: {phase}",
            )
        receipt_path = report_dir / "receipt.json"
        write_json(receipt_path, receipt)
        write_json(
            report_dir / "report.json",
            {
                "schema": RECEIPT_SCHEMA,
                "migrationId": MIGRATION_ID,
                "environment": environment,
                "phase": phase,
                "status": receipt["status"],
                "receiptRef": relpath(receipt_path),
                "receiptDigest": receipt["receiptDigest"],
                "writeSet": receipt["writeSet"],
            },
        )
        blocked = receipt["status"] == "GATE_BLOCK"
        return {
            "exitCode": 2 if blocked else 0,
            "summary": (
                f"stackctl migration {MIGRATION_ID} {phase} is GATE_BLOCK"
                if blocked
                else f"stackctl migration {MIGRATION_ID} {phase} passed"
            ),
            "details": [
                f"receipt: {relpath(receipt_path)}",
                f"receiptDigest: {receipt['receiptDigest']}",
                "environment writes executed by control plane: 0",
                f"declared writeSet steps: {len(receipt['writeSet'])}",
            ],
            "reportDir": relpath(report_dir),
            "receiptRef": relpath(receipt_path),
            "receiptDigest": receipt["receiptDigest"],
        }
    except MigrationControlError as exc:
        if report_dir is not None:
            failure_path = report_dir / "report.json"
            write_json(
                failure_path,
                {
                    "schema": RECEIPT_SCHEMA,
                    "migrationId": MIGRATION_ID,
                    "environment": environment,
                    "phase": phase,
                    "status": "GATE_BLOCK",
                    "errorCode": exc.code,
                    "details": [str(exc)],
                    "writeSet": [],
                },
            )
        result = {
            "exitCode": 2,
            "summary": (f"stackctl migration {MIGRATION_ID} {phase} is GATE_BLOCK"),
            "details": [f"{exc.code}: {exc}", "environment writes: 0"],
        }
        if report_dir is not None:
            result["reportDir"] = relpath(report_dir)
        return result


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    migration = subparsers.add_parser(
        "migration",
        help="受控跨服务 target-only 迁移证据控制面",
    )
    migration_commands = migration.add_subparsers(
        dest="migration_command",
        required=True,
    )
    travel = migration_commands.add_parser(
        MIGRATION_ID,
        help="travel-service 到 Gathering 的 target-only 迁移控制面",
    )
    travel.add_argument("--report-dir", default=argparse.SUPPRESS)
    travel.add_argument("--env", choices=ENVIRONMENTS, required=True)
    travel.add_argument("--phase", choices=PHASES, required=True)
    travel.add_argument(
        "--source-snapshot",
        default="",
        help="显式只读 travel source snapshot；inventory/dry-run/parity 必需",
    )
    travel.add_argument(
        "--target-snapshot",
        default="",
        help="显式只读 Gathering target snapshot；parity 必需",
    )
    travel.add_argument(
        "--inventory-receipt",
        default="",
        help="已通过且摘要封存的 inventory migration receipt；cutover 必需",
    )
    travel.add_argument(
        "--parity-receipt",
        default="",
        help="100%% parity migration receipt；cutover 必需",
    )
    travel.add_argument(
        "--target-backup-receipt",
        default="",
        help="签名 target-only 备份 evidence；cutover 必需",
    )
    travel.add_argument(
        "--source-freeze-receipt",
        default="",
        help="签名且不允许恢复源写的 source freeze evidence；cutover 必需",
    )
    travel.add_argument(
        "--target-command-receipt",
        default="",
        help="签名 canonical target command/import evidence；cutover 必需",
    )
    travel.add_argument(
        "--config-candidate-digest",
        default="",
        help="待激活 target-only 配置候选摘要；cutover 必需",
    )
    travel.add_argument(
        "--approval-receipt",
        default="",
        help="保护环境写入的外部签名审批 evidence；cutover/rollback 必需",
    )
    travel.add_argument(
        "--config-activation-receipt",
        default="",
        help="外部执行 target config activation 的签名 evidence；cutover 完成必需",
    )
    travel.add_argument(
        "--cutover-receipt",
        default="",
        help="已通过且外部执行完成的 cutover receipt；rollback 必需",
    )
    travel.add_argument(
        "--rollback-mode",
        choices=ROLLBACK_MODES,
        default="",
        help="仅允许 target app/config 或 target snapshot rollback",
    )
    travel.add_argument(
        "--rollback-candidate-digest",
        default="",
        help="rollback app/config 或 snapshot 候选摘要",
    )
    travel.add_argument(
        "--target-restore-receipt",
        default="",
        help="外部审批后执行 target restore 的签名 evidence",
    )
    travel.add_argument(
        "--post-restore-parity-receipt",
        default="",
        help="restore 后 100%% parity migration receipt",
    )


def command(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "migration_command", "") != MIGRATION_ID:
        return {
            "exitCode": 2,
            "summary": "stackctl migration command is GATE_BLOCK",
            "details": ["unknown migration command", "environment writes: 0"],
        }
    return execute(args)
