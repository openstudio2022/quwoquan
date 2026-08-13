"""stackctl repair 内容恢复域: active content release outbox 修复与
媒体处理死信索引迁移。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- `_repair_active_content_release_outbox`;
- `_repair_media_processing_dead_letter_indexes`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess

from pathlib import Path
from typing import Any


def _repair_active_content_release_outbox(
    args: argparse.Namespace,
    *,
    environment: str,
    target_name: str,
    report_dir: Path,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report: dict[str, Any] = {
        "schema": "stackctl-active-content-release-outbox-repair",
        "command": "repair",
        "target": target_name,
        "fix": "repair-active-content-release-outbox",
        "status": "gate_block",
        "confirmation": bool(
            getattr(
                args,
                "confirm_active_content_release_outbox_repair",
                False,
            )
        ),
        "expectedOutboxRepairCount": int(
            getattr(args, "expected_outbox_repair_count", -1)
        ),
        "runtimeServices": ["mongodb", "mongo-init", "content-service:run"],
        "apiStarted": False,
        "destructiveRepairAttempted": False,
        "destructiveRepairOutcome": "not_started",
        "destructiveRepairPerformed": False,
        "destructiveActions": [],
        "resourceReleaseIssues": [],
        "steps": [],
    }
    details: list[str] = []
    compose_prefix: list[str] = []
    environment_values: dict[str, str] = {}
    repair_succeeded = False

    def finish(exit_code: int) -> dict[str, Any]:
        status = "passed" if exit_code == 0 else "gate_block"
        report["status"] = status
        report["details"] = details
        _stackctl.write_json(report_dir / "report.json", report)
        summary = (
            f"active Content release outbox repair passed for {target_name}"
            if exit_code == 0
            else f"active Content release outbox repair is GATE_BLOCK for {target_name}"
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target=target_name,
            status="ok" if exit_code == 0 else "failed",
            summary=summary,
            details=details,
            extra={
                "fix": "repair-active-content-release-outbox",
                "expectedOutboxRepairCount": report[
                    "expectedOutboxRepairCount"
                ],
                "candidateDigest": str(report.get("candidateDigest") or ""),
            },
        )
        return {
            "exitCode": exit_code,
            "summary": summary,
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
        }

    if target_name != "alpha-local":
        details.append(
            "repair-active-content-release-outbox is currently limited to alpha-local"
        )
        return finish(2)
    if not report["confirmation"]:
        details.append(
            "--confirm-active-content-release-outbox-repair is required before runtime or Mongo access"
        )
        return finish(2)
    expected_count = int(report["expectedOutboxRepairCount"])
    if expected_count < 0:
        details.append("--expected-outbox-repair-count must be non-negative")
        return finish(2)
    source_import_arg = str(
        getattr(args, "content_import_report", "") or ""
    ).strip()
    if not source_import_arg:
        details.append("--content-import-report is required")
        return finish(2)

    try:
        with _stackctl._local_stack_operation_lock(target_name):
            active_leases = _stackctl.active_consumer_leases(target_name)
            if active_leases:
                raise ValueError(
                    "active Content outbox repair requires zero consumer leases"
                )
            startup = _stackctl.load_startup_attempt(target_name)
            if startup is not None and startup.get("status") != "stopped":
                raise ValueError(
                    "active Content outbox repair requires an absent or stopped runtime receipt"
                )
            candidate_snapshot = _stackctl.active_deployment_candidate_snapshot(target_name)
            if candidate_snapshot is None:
                raise ValueError("active immutable candidate is required")
            baseline_id, candidate_root, candidate_manifest = _stackctl._fixed_candidate_identity(
                candidate_snapshot,
                environment_name=environment,
                target_name=target_name,
            )
            source_import_path = Path(source_import_arg).expanduser().resolve()
            allowed_import_root = (
                _stackctl.output_root()
                / "env"
                / environment
                / "runs"
                / "data-release"
            ).resolve()
            if not source_import_path.is_relative_to(allowed_import_root):
                raise ValueError(
                    "Content import report must belong to canonical environment data-release output"
                )
            source_import = (
                _stackctl.active_content_release_outbox_repair.validate_source_import_report(
                    source_import_path,
                    environment=environment,
                )
            )
            legacy_deletion_count = int(source_import["legacyDeletionCount"])
            if expected_count not in {0, legacy_deletion_count}:
                raise ValueError(
                    "expected outbox repair count must be either zero or the "
                    "source import legacy deletion count"
                )
            release_binding = (
                _stackctl.active_content_release_outbox_repair.validate_candidate_release_binding(
                    candidate_snapshot,
                    source_import,
                )
            )
            release_root = Path(str(release_binding["releaseRoot"])).resolve()
            canonical_data_root = (_stackctl.output_root() / "data" / "releases").resolve()
            if not release_root.is_relative_to(canonical_data_root):
                raise ValueError(
                    "candidate release root must belong to canonical Data release output"
                )
            creator_receipt = (
                _stackctl.active_content_release_outbox_repair.validate_creator_receipt(
                    source_import_path,
                    environment=environment,
                    release_id=str(release_binding["releaseId"]),
                )
            )
            compose_files = (
                _stackctl.active_content_release_outbox_repair.topology_compose_files(
                    candidate_root,
                    candidate_manifest,
                )
            )
            runtime_inputs = _stackctl.active_content_release_outbox_repair.materialize_candidate_runtime_inputs(
                candidate_root,
                report_dir,
                environment=environment,
            )
            tls_evidence = _stackctl.verify_certificate(target_name)
            certificate = str(tls_evidence.get("certificate") or "").strip()
            private_key = str(tls_evidence.get("privateKey") or "").strip()
            if not certificate or not private_key:
                raise ValueError(
                    "active Content outbox repair requires verified local-managed TLS"
                )
            provider_binding, observability_binding = (
                _stackctl._candidate_bindings_from_snapshot(
                    candidate_snapshot,
                    environment_name=environment,
                    target_name=target_name,
                )
            )
            environment_values = _stackctl._gamma_env_from_port_manifest(
                _stackctl.load_environment_topology(),
                target_name,
            )
            environment_values.update(runtime_inputs["environment"])
            environment_values.update(
                _stackctl._provider_runtime_launch_environment(
                    provider_binding["providerRuntime"],
                    candidate_root=provider_binding["candidateRoot"],
                    workload="content-release",
                )
            )
            environment_values.update(
                _stackctl._observability_log_sink_launch_environment(
                    observability_binding["composition"],
                    environment_name=environment,
                    target_name=target_name,
                    candidate_root=observability_binding["candidateRoot"],
                    workload="content-release",
                )
            )
            environment_values.update(
                {
                    "QWQ_RUN_ROOT": str(report_dir.resolve()),
                    "QWQ_OBSERVABILITY_RUN_ROOT": str(
                        (report_dir / "observability").resolve()
                    ),
                    "QWQ_WORKLOAD": "content-release",
                    "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "0",
                    "QWQ_RELEASE_CANDIDATE_DIGEST": baseline_id,
                    _stackctl.RUNTIME_CANDIDATE_ROOT_ENV: str(candidate_root),
                    "QWQ_PUBLIC_TLS_CERT_FILE": certificate,
                    "QWQ_PUBLIC_TLS_KEY_FILE": private_key,
                }
            )
            _stackctl._bind_gamma_down_parse_environment(environment_values)
            image_composition = _stackctl._bind_gamma_packaged_service_image_refs(
                environment,
                environment_values,
                candidate_snapshot=candidate_snapshot,
            )
            _stackctl._bind_gamma_packaged_configuration_digest(
                environment,
                environment_values,
                image_composition,
            )
            compose_project = _stackctl._formal_release_compose_project_name(target_name)
            environment_values["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"] = compose_project
            compose_prefix = [
                "docker",
                "compose",
                "-p",
                compose_project,
                *_stackctl.compose_file_args(compose_files),
            ]
            report.update(
                {
                    "candidateDigest": baseline_id,
                    "candidateRoot": str(candidate_root),
                    "candidateManifestDigest": _stackctl._sha256_file(
                        candidate_root / "manifest.json"
                    ),
                    "releaseBinding": release_binding,
                    "sourceImport": source_import,
                    "creatorReceipt": creator_receipt,
                    "startupReceipt": startup,
                    "consumerLeases": [],
                    "composeProject": compose_project,
                    "composeFiles": [str(path) for path in compose_files],
                    "runtimeInputs": runtime_inputs["evidence"],
                    "candidateReleaseInputClassification": candidate_manifest.get(
                        "releaseInputClassification"
                    ),
                }
            )

            def execute(name: str, argv: list[str]) -> None:
                result = _stackctl.run(
                    argv,
                    env=environment_values,
                    timeout_seconds=300,
                )
                step = {
                    "name": name,
                    "argv": argv,
                    "exitCode": result.returncode,
                    "stdoutSha256": "sha256:"
                    + hashlib.sha256(result.stdout.encode()).hexdigest(),
                    "stderrSha256": "sha256:"
                    + hashlib.sha256(result.stderr.encode()).hexdigest(),
                }
                report["steps"].append(step)
                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr.strip()
                        or result.stdout.strip()
                        or f"{name} exited with status {result.returncode}"
                    )

            execute("compose-config", [*compose_prefix, "config", "--services"])
            execute(
                "mongo-start",
                [*compose_prefix, "up", "-d", "--wait", "mongodb"],
            )
            execute(
                "mongo-init",
                [*compose_prefix, "run", "--rm", "--no-deps", "mongo-init"],
            )
            repair_report_path = report_dir / "content-import-repair.json"
            import_argv = [
                *compose_prefix,
                "run",
                "--rm",
                "--no-deps",
                "-v",
                f"{release_root}:/repair/release:ro",
                "-v",
                f"{creator_receipt['path']}:/repair/creator-import.json:ro",
                "-v",
                f"{source_import_path}:/repair/source-import.json:ro",
                "-v",
                f"{report_dir.resolve()}:/repair/report",
                "content-service",
                "/usr/local/bin/content-import",
                "--release-root",
                "/repair/release",
                "--mongo-uri",
                "mongodb://mongodb:27017",
                "--env",
                environment,
                "--mode",
                "sync",
                "--delete-policy",
                "tombstone",
                "--source-owner",
                "qwq_data",
                "--creator-receipt",
                "/repair/creator-import.json",
                "--media-image-base-url",
                environment_values["LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL"],
                "--media-video-base-url",
                environment_values["LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL"],
                "--media-avatar-base-url",
                environment_values["LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL"],
                "--require-replay",
                "--replay-source-import-report",
                "/repair/source-import.json",
                "--expected-outbox-repair-count",
                str(expected_count),
                "--report",
                "/repair/report/content-import-repair.json",
            ]
            report["destructiveRepairAttempted"] = True
            report["destructiveRepairOutcome"] = "unknown"
            report["destructiveRepairPerformed"] = None
            execute("content-import-repair", import_argv)
            repair_evidence = (
                _stackctl.active_content_release_outbox_repair.validate_repair_report(
                    repair_report_path,
                    environment=environment,
                    release_id=str(release_binding["releaseId"]),
                    manifest_digest=str(release_binding["manifestDigest"]),
                    expected_repair_count=expected_count,
                    expected_post_binding_count=int(
                        source_import["postBindingCount"]
                    ),
                    expected_post_bindings_digest=str(
                        source_import["postBindingsDigest"]
                    ),
                )
            )
            report["repairEvidence"] = repair_evidence
            report["destructiveRepairPerformed"] = expected_count > 0
            report["destructiveRepairOutcome"] = "confirmed"
            report["destructiveActions"] = (
                repair_evidence["repairs"] if expected_count > 0 else []
            )
            source_import_after = (
                _stackctl.active_content_release_outbox_repair.validate_source_import_report(
                    source_import_path,
                    environment=environment,
                )
            )
            release_binding_after = (
                _stackctl.active_content_release_outbox_repair.validate_candidate_release_binding(
                    candidate_snapshot,
                    source_import_after,
                )
            )
            creator_receipt_after = (
                _stackctl.active_content_release_outbox_repair.validate_creator_receipt(
                    source_import_path,
                    environment=environment,
                    release_id=str(release_binding["releaseId"]),
                )
            )
            compose_files_after = (
                _stackctl.active_content_release_outbox_repair.topology_compose_files(
                    candidate_root,
                    candidate_manifest,
                )
            )
            if (
                source_import_after != source_import
                or release_binding_after != release_binding
                or creator_receipt_after != creator_receipt
                or compose_files_after != compose_files
                or _stackctl._sha256_file(candidate_root / "manifest.json")
                != report["candidateManifestDigest"]
            ):
                raise ValueError(
                    "candidate/release/import identity changed during repair"
                )
            _stackctl.assert_active_deployment_candidate_snapshot(candidate_snapshot)
            repair_succeeded = True
            details.extend(
                [
                    f"candidate={baseline_id}",
                    f"release={release_binding['releaseId']}",
                    f"repaired={repair_evidence['repairCount']}",
                    "Mongo-only repair completed; API/relay/consumer remained stopped",
                ]
            )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        details.append(str(exc))
    finally:
        if compose_prefix:
            cleanup_argv = [*compose_prefix, "down", "--remove-orphans"]
            try:
                cleanup = _stackctl.run(
                    cleanup_argv,
                    env=environment_values,
                    timeout_seconds=180,
                )
            except OSError as exc:
                cleanup = subprocess.CompletedProcess(
                    cleanup_argv,
                    2,
                    "",
                    str(exc),
                )
            report["steps"].append(
                {
                    "name": "mongo-teardown",
                    "argv": cleanup_argv,
                    "exitCode": cleanup.returncode,
                    "stdoutSha256": "sha256:"
                    + hashlib.sha256(cleanup.stdout.encode()).hexdigest(),
                    "stderrSha256": "sha256:"
                    + hashlib.sha256(cleanup.stderr.encode()).hexdigest(),
                    "volumesPurged": False,
                }
            )
            if cleanup.returncode != 0:
                issue = (
                    cleanup.stderr.strip()
                    or cleanup.stdout.strip()
                    or "Mongo-only repair teardown failed"
                )
                report["resourceReleaseIssues"].append(issue)
                details.append(issue)
                repair_succeeded = False
    return finish(0 if repair_succeeded else 2)


def _repair_media_processing_dead_letter_indexes(
    args: argparse.Namespace,
    *,
    environment: str,
    target_name: str,
    report_dir: Path,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    expected_drop_count = int(
        getattr(args, "expected_retired_index_drop_count", -1)
    )
    report: dict[str, Any] = {
        "schema": "stackctl-media-processing-dead-letter-index-migration.v1",
        "command": "repair",
        "target": target_name,
        "fix": "repair-media-processing-dead-letter-indexes",
        "status": "gate_block",
        "confirmation": bool(
            getattr(
                args,
                "confirm_media_processing_dead_letter_index_migration",
                False,
            )
        ),
        "expectedRetiredIndexDropCount": expected_drop_count,
        "runtimeServices": ["mongodb", "mongo-init", "content-service:run"],
        "apiStarted": False,
        "storageMigrationMode": "quiesced_atomic",
        "destructiveRepairAttempted": False,
        "destructiveRepairOutcome": "not_started",
        "destructiveRepairPerformed": False,
        "destructiveActions": [],
        "resourceReleaseIssues": [],
        "steps": [],
    }
    details: list[str] = []
    compose_prefix: list[str] = []
    environment_values: dict[str, str] = {}
    migration_succeeded = False

    def finish(exit_code: int) -> dict[str, Any]:
        status = "passed" if exit_code == 0 else "gate_block"
        report["status"] = status
        report["details"] = details
        _stackctl.write_json(report_dir / "report.json", report)
        summary = (
            "MediaAsset retired dead-letter index migration passed for "
            f"{target_name}"
            if exit_code == 0
            else "MediaAsset retired dead-letter index migration is GATE_BLOCK "
            f"for {target_name}"
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target=target_name,
            status="ok" if exit_code == 0 else "failed",
            summary=summary,
            details=details,
            extra={
                "fix": "repair-media-processing-dead-letter-indexes",
                "expectedRetiredIndexDropCount": expected_drop_count,
                "candidateDigest": str(report.get("candidateDigest") or ""),
            },
        )
        return {
            "exitCode": exit_code,
            "summary": summary,
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
        }

    if target_name != "alpha-local":
        details.append(
            "repair-media-processing-dead-letter-indexes is currently limited to alpha-local"
        )
        return finish(2)
    if not report["confirmation"]:
        details.append(
            "--confirm-media-processing-dead-letter-index-migration is required "
            "before runtime or Mongo access"
        )
        return finish(2)
    if expected_drop_count not in {0, 2}:
        details.append(
            "--expected-retired-index-drop-count must be 0 for replay or 2 for "
            "the first migration"
        )
        return finish(2)

    try:
        with _stackctl._local_stack_operation_lock(target_name):
            active_leases = _stackctl.active_consumer_leases(target_name)
            if active_leases:
                raise ValueError(
                    "MediaAsset dead-letter index migration requires zero consumer leases"
                )
            startup = _stackctl.load_startup_attempt(target_name)
            if startup is not None and startup.get("status") != "stopped":
                raise ValueError(
                    "MediaAsset dead-letter index migration requires an absent or "
                    "stopped runtime receipt"
                )
            candidate_snapshot = _stackctl.active_deployment_candidate_snapshot(target_name)
            if candidate_snapshot is None:
                raise ValueError("active immutable candidate is required")
            baseline_id, candidate_root, candidate_manifest = _stackctl._fixed_candidate_identity(
                candidate_snapshot,
                environment_name=environment,
                target_name=target_name,
            )
            compose_files = (
                _stackctl.active_content_release_outbox_repair.topology_compose_files(
                    candidate_root,
                    candidate_manifest,
                )
            )
            runtime_inputs = (
                _stackctl.active_content_release_outbox_repair.materialize_candidate_runtime_inputs(
                    candidate_root,
                    report_dir,
                    environment=environment,
                )
            )
            tls_evidence = _stackctl.verify_certificate(target_name)
            certificate = str(tls_evidence.get("certificate") or "").strip()
            private_key = str(tls_evidence.get("privateKey") or "").strip()
            if not certificate or not private_key:
                raise ValueError(
                    "MediaAsset dead-letter index migration requires verified local-managed TLS"
                )
            provider_binding, observability_binding = (
                _stackctl._candidate_bindings_from_snapshot(
                    candidate_snapshot,
                    environment_name=environment,
                    target_name=target_name,
                )
            )
            environment_values = _stackctl._gamma_env_from_port_manifest(
                _stackctl.load_environment_topology(),
                target_name,
            )
            environment_values.update(runtime_inputs["environment"])
            environment_values.update(
                _stackctl._provider_runtime_launch_environment(
                    provider_binding["providerRuntime"],
                    candidate_root=provider_binding["candidateRoot"],
                    workload="content-release",
                )
            )
            environment_values.update(
                _stackctl._observability_log_sink_launch_environment(
                    observability_binding["composition"],
                    environment_name=environment,
                    target_name=target_name,
                    candidate_root=observability_binding["candidateRoot"],
                    workload="content-release",
                )
            )
            environment_values.update(
                {
                    "QWQ_RUN_ROOT": str(report_dir.resolve()),
                    "QWQ_OBSERVABILITY_RUN_ROOT": str(
                        (report_dir / "observability").resolve()
                    ),
                    "QWQ_WORKLOAD": "content-release",
                    "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "0",
                    "QWQ_RELEASE_CANDIDATE_DIGEST": baseline_id,
                    _stackctl.RUNTIME_CANDIDATE_ROOT_ENV: str(candidate_root),
                    "QWQ_PUBLIC_TLS_CERT_FILE": certificate,
                    "QWQ_PUBLIC_TLS_KEY_FILE": private_key,
                }
            )
            _stackctl._bind_gamma_down_parse_environment(environment_values)
            image_composition = _stackctl._bind_gamma_packaged_service_image_refs(
                environment,
                environment_values,
                candidate_snapshot=candidate_snapshot,
            )
            _stackctl._bind_gamma_packaged_configuration_digest(
                environment,
                environment_values,
                image_composition,
            )
            compose_project = _stackctl._formal_release_compose_project_name(target_name)
            environment_values["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"] = compose_project
            compose_prefix = [
                "docker",
                "compose",
                "-p",
                compose_project,
                *_stackctl.compose_file_args(compose_files),
            ]
            candidate_manifest_digest = _stackctl._sha256_file(
                candidate_root / "manifest.json"
            )
            report.update(
                {
                    "candidateDigest": baseline_id,
                    "candidateRoot": str(candidate_root),
                    "candidateManifestDigest": candidate_manifest_digest,
                    "startupReceipt": startup,
                    "consumerLeases": [],
                    "composeProject": compose_project,
                    "composeFiles": [str(path) for path in compose_files],
                    "runtimeInputs": runtime_inputs["evidence"],
                    "candidateReleaseInputClassification": candidate_manifest.get(
                        "releaseInputClassification"
                    ),
                }
            )

            def execute(name: str, argv: list[str]) -> None:
                result = _stackctl.run(argv, env=environment_values, timeout_seconds=300)
                step = {
                    "name": name,
                    "argv": argv,
                    "exitCode": result.returncode,
                    "stdoutSha256": "sha256:"
                    + hashlib.sha256(result.stdout.encode()).hexdigest(),
                    "stderrSha256": "sha256:"
                    + hashlib.sha256(result.stderr.encode()).hexdigest(),
                }
                report["steps"].append(step)
                if result.returncode != 0:
                    raise RuntimeError(
                        result.stderr.strip()
                        or result.stdout.strip()
                        or f"{name} exited with status {result.returncode}"
                    )

            execute("compose-config", [*compose_prefix, "config", "--services"])
            execute(
                "mongo-start",
                [*compose_prefix, "up", "-d", "--wait", "mongodb"],
            )
            execute(
                "mongo-init",
                [*compose_prefix, "run", "--rm", "--no-deps", "mongo-init"],
            )
            migration_report_path = (
                report_dir / "media-processing-dead-letter-index-migration.json"
            )
            migration_argv = [
                *compose_prefix,
                "run",
                "--rm",
                "--no-deps",
                "-e",
                "MONGO_URI=mongodb://mongodb:27017",
                "-e",
                "CONTENT_MONGO_DATABASE=quwoquan_content",
                "-e",
                "QWQ_STORAGE_MIGRATION_MODE=quiesced_atomic",
                "-v",
                f"{report_dir.resolve()}:/migration/report",
                "content-service",
                "/usr/local/bin/migrate-media-processing-dead-letter-indexes",
                "--expected-drop-count",
                str(expected_drop_count),
                "--report",
                "/migration/report/media-processing-dead-letter-index-migration.json",
            ]
            report["destructiveRepairAttempted"] = True
            report["destructiveRepairOutcome"] = "unknown"
            report["destructiveRepairPerformed"] = None
            execute("media-processing-dead-letter-index-migration", migration_argv)
            raw_migration_report = json.loads(
                migration_report_path.read_text(encoding="utf-8")
            )
            required_report_fields = {
                "schema",
                "status",
                "database",
                "migrationMode",
                "expectedDropCount",
                "droppedIndexes",
                "retiredIndexesAbsent",
            }
            if (
                not isinstance(raw_migration_report, dict)
                or set(raw_migration_report) != required_report_fields
                or raw_migration_report.get("schema")
                != "quwoquan.content.media_processing_dead_letter_index_migration.v1"
                or raw_migration_report.get("status") != "passed"
                or raw_migration_report.get("database") != "quwoquan_content"
                or raw_migration_report.get("migrationMode") != "quiesced_atomic"
                or raw_migration_report.get("expectedDropCount")
                != expected_drop_count
                or raw_migration_report.get("retiredIndexesAbsent") is not True
            ):
                raise ValueError(
                    "MediaAsset dead-letter index migration report identity mismatch"
                )
            dropped_indexes = raw_migration_report.get("droppedIndexes")
            if (
                not isinstance(dropped_indexes, list)
                or len(dropped_indexes) != expected_drop_count
                or len(set(dropped_indexes)) != expected_drop_count
                or any(
                    not isinstance(name, str) or not name.strip()
                    for name in dropped_indexes
                )
            ):
                raise ValueError(
                    "MediaAsset dead-letter index migration dropped index set mismatch"
                )
            report["migrationEvidence"] = {
                "path": str(migration_report_path.resolve()),
                "sha256": _stackctl._sha256_file(migration_report_path),
                **raw_migration_report,
            }
            report["destructiveRepairPerformed"] = expected_drop_count > 0
            report["destructiveRepairOutcome"] = "confirmed"
            report["destructiveActions"] = [
                {"action": "drop_index", "index": name}
                for name in dropped_indexes
            ]
            compose_files_after = (
                _stackctl.active_content_release_outbox_repair.topology_compose_files(
                    candidate_root,
                    candidate_manifest,
                )
            )
            if (
                compose_files_after != compose_files
                or _stackctl._sha256_file(candidate_root / "manifest.json")
                != candidate_manifest_digest
            ):
                raise ValueError(
                    "candidate or runtime topology identity changed during migration"
                )
            _stackctl.assert_active_deployment_candidate_snapshot(candidate_snapshot)
            migration_succeeded = True
            details.extend(
                [
                    f"candidate={baseline_id}",
                    f"dropped={expected_drop_count}",
                    "Mongo-only migration completed; API/relay/consumer remained stopped",
                ]
            )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        details.append(str(exc))
    finally:
        if compose_prefix:
            cleanup_argv = [*compose_prefix, "down", "--remove-orphans"]
            try:
                cleanup = _stackctl.run(
                    cleanup_argv,
                    env=environment_values,
                    timeout_seconds=180,
                )
            except OSError as exc:
                cleanup = subprocess.CompletedProcess(
                    cleanup_argv,
                    2,
                    "",
                    str(exc),
                )
            report["steps"].append(
                {
                    "name": "mongo-teardown",
                    "argv": cleanup_argv,
                    "exitCode": cleanup.returncode,
                    "stdoutSha256": "sha256:"
                    + hashlib.sha256(cleanup.stdout.encode()).hexdigest(),
                    "stderrSha256": "sha256:"
                    + hashlib.sha256(cleanup.stderr.encode()).hexdigest(),
                    "volumesPurged": False,
                }
            )
            if cleanup.returncode != 0:
                issue = (
                    cleanup.stderr.strip()
                    or cleanup.stdout.strip()
                    or "Mongo-only migration teardown failed"
                )
                report["resourceReleaseIssues"].append(issue)
                details.append(issue)
                migration_succeeded = False
    return finish(0 if migration_succeeded else 2)
