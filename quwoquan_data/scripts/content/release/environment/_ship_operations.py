"""Immutable release 的 apply、rollback 与 consumer verification 操作。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from content.release.environment._ship_operation_dependencies import (
    ShipOperationDependencies,
)
from content.release.environment.consistency import (
    report_to_text,
    scan_release_contract,
)
from content.release.environment.homepage_verification_cases import (
    HomepageVerificationCaseError,
)
from content.release.environment.importers import (
    assert_content_release_evidence_unchanged,
)
from content.release.environment.readiness import ShipReadinessPhase
from content.release.environment.run_evidence import (
    read_environment_result,
    validate_path_segment,
)
from content.release.model import (
    DeletePolicy,
    DeploymentEnvironment,
    EvidenceStatus,
    ImportMode,
)
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import read_json, write_json
from core.paths import release_ref
from core.release_layout import payload_file


_SENSITIVE_ERROR_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|access[_-]?token|refresh[_-]?token|token|password|"
    r"secret|body|query)\b\s*[:=]\s*(?:Bearer\s+)?(?:\{[^}]*\}|\[[^]]*\]|"
    r'"[^"]*"|\'[^\']*\'|[^\s,;]+)'
)
_SENSITIVE_ERROR_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_SENSITIVE_URL_CREDENTIALS = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@"
)


def _bounded_error(
    error: Exception | SystemExit,
    *,
    limit: int = 1024,
) -> str:
    """Return one bounded, redacted diagnostic line without traceback text."""

    message = " ".join(str(error).splitlines()).strip()
    message = _SENSITIVE_ERROR_BEARER.sub("Bearer [REDACTED]", message)
    message = _SENSITIVE_URL_CREDENTIALS.sub(r"\1[REDACTED]@", message)
    message = _SENSITIVE_ERROR_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        message,
    )
    return (message or type(error).__name__)[:limit]


def _write_terminal_result(
    *,
    dependencies: ShipOperationDependencies,
    run: Path,
    document: dict[str, object],
) -> None:
    dependencies.write_verification_result(run / "result.json", document)


def _record_failed_result(
    *,
    dependencies: ShipOperationDependencies,
    run: Path,
    base_result: dict[str, object],
    failed_stage: str,
    error: Exception | SystemExit,
) -> Exception | None:
    try:
        _write_terminal_result(
            dependencies=dependencies,
            run=run,
            document={
                **base_result,
                "status": ReleaseRunStatus.FAILED,
                "failedStage": failed_stage,
                "error": _bounded_error(error),
            },
        )
    except Exception as receipt_error:  # Preserve the operation as the first cause.
        return receipt_error
    return None


def _failed_receipt_note(
    *,
    error: Exception | SystemExit,
    receipt_error: Exception | None,
) -> None:
    if receipt_error is not None:
        error.add_note(
            f"{_bounded_error(error)}; failed result evidence error: "
            f"{_bounded_error(receipt_error)}"
        )


def _release_admission(
    args: argparse.Namespace,
    dependencies: ShipOperationDependencies,
):
    admission = getattr(args, "release_admission", None)
    if admission is None:
        admission = dependencies.admit_release(args)
    if admission is None:
        raise SystemExit("[ship] GATE_BLOCK sealed release admission is missing")
    return admission


def _required_adapter(dependencies: ShipOperationDependencies, name: str):
    adapter = getattr(dependencies, name, None)
    if adapter is None:
        raise SystemExit(
            f"[ship] GATE_BLOCK Content release-control adapter missing: {name}"
        )
    return adapter


def _require_owner_local_staging_admission(
    *,
    dependencies: ShipOperationDependencies,
    release: Path,
    contract: dict[str, object],
    environment: str,
    action: str,
) -> None:
    adapter = getattr(dependencies, "require_owner_local_staging_admission", None)
    if adapter is None:
        raise SystemExit(
            "[ship] GATE_BLOCK cross-owner live release requires verified "
            "owner-local staged candidates for tag, creator, content, and homepage"
        )
    adapter(
        release=release,
        contract=contract,
        environment=environment,
        action=action,
    )


def _lifecycle_evidence(admission: object) -> dict[str, object]:
    header = read_json(payload_file(admission.release, "release.json"))
    return {
        "releaseClass": str(header.get("releaseClass") or ""),
        "productLifecycleState": str(header.get("productLifecycleState") or ""),
        "containsUnverifiedAssets": bool(header.get("containsUnverifiedAssets")),
        "manifestDigest": admission.manifest_digest,
    }


def _import_evidence_refs(
    run: Path, dependencies: ShipOperationDependencies
) -> dict[str, str]:
    return {
        "homepageVerificationCasesRef": "",
        "tagImportReportRef": "",
        "creatorImportReportRef": "",
        "contentImportReportRef": "",
        "homepageImportReportRef": "",
        "coverageReceiptRef": "",
    }


def apply_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    admission = _release_admission(args, dependencies)
    release_id = validate_path_segment(admission.release_id, label="release_id")
    release, contract = admission.release, admission.contract
    lifecycle_evidence = _lifecycle_evidence(admission)
    env = str(args.env)
    if (
        not env
        or env != env.strip()
        or "," in env
        or any(character.isspace() for character in env)
    ):
        raise SystemExit("[ship] apply --env 必须且只能是一个环境")
    if (
        env == DeploymentEnvironment.PROD
        and args.import_to_db
        and not args.dry_run
        and not args.confirm_prod_apply
    ):
        raise SystemExit("[ship] prod apply 需要 --confirm-prod-apply")
    preflight = scan_release_contract(contract, release_root=release, phase="preflight")
    print(report_to_text(preflight))
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] release consistency preflight failed")
    full_sync = bool(args.full_sync)
    if dependencies.release_requires_full_sync(release) and not full_sync:
        raise SystemExit("[ship] immutable release requires --full-sync")
    dependencies.assert_environment_release_policy(
        release=release, contract=contract, environment=env
    )
    target = dependencies.resolve_environment_release_target(env)
    dependencies.assert_target_action_allowed(
        target=target,
        import_to_db=bool(args.import_to_db),
        dry_run=bool(args.dry_run),
        action="apply",
    )
    run_id = validate_path_segment(
        str(args.run_id or f"apply-{dependencies.now_compact()}"), label="run_id"
    )
    run = dependencies.create_run(env, release_id, run_id, kind=ReleaseRunKind.APPLY)
    base_result: dict[str, object] = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        **lifecycle_evidence,
        **admission.result_envelope(),
        "runId": run_id,
    }
    refs = _import_evidence_refs(run, dependencies)
    failed_stage = "owner_local_staging_admission"
    try:
        if args.import_to_db and not args.dry_run:
            _require_owner_local_staging_admission(
                dependencies=dependencies,
                release=release,
                contract=contract,
                environment=env,
                action="apply",
            )
            failed_stage = "environment_readiness"
            dependencies.require_environment_readiness(
                environment=target.environment,
                phase=ShipReadinessPhase.IMPORT,
                run=run,
                release_id=release_id,
                manifest_digest=admission.manifest_digest,
            )
        failed_stage = "consistency_preflight_evidence"
        write_json(run / "consistency-preflight.json", preflight)
        if (
            target.media_sync_root is not None
            and args.import_to_db
            and not args.dry_run
        ):
            failed_stage = "media_sync"
            dependencies.sync_media(
                release=release, destination=str(target.media_sync_root), run=run
            )
        candidate_evidence: dict[str, object] = {}
        if args.import_to_db:
            failed_stage = "tag_import"
            tag_receipt = dependencies.run_tag_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                dry_run=bool(args.dry_run),
            )
            refs["tagImportReportRef"] = tag_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            failed_stage = "creator_import"
            creator_receipt = dependencies.run_creator_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                postgres_dsn=target.user_postgres_dsn,
                media_avatar_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
            refs["creatorImportReportRef"] = creator_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            failed_stage = "content_candidate_stage"
            content_receipt = dependencies.run_content_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                media_avatar_base_url=target.media_delivery_base_url,
                media_image_base_url=target.media_delivery_base_url,
                media_video_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
                delete_policy=DeletePolicy.TOMBSTONE
                if full_sync
                else DeletePolicy.NONE,
                creator_receipt=creator_receipt,
            )
            refs["contentImportReportRef"] = content_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            if not args.dry_run:
                failed_stage = "content_candidate_query"
                candidate = _required_adapter(
                    dependencies, "query_content_release_candidate"
                )(
                    env=env,
                    mongo_uri=target.mongo_uri,
                    release_id=release_id,
                    manifest_digest=admission.manifest_digest,
                    report_path=run / "content-candidate-receipt.json",
                    output_root=dependencies.output_root,
                )
                candidate_evidence = {
                    "contentCandidateReceiptRef": candidate.ref,
                    "contentCandidateReceiptDigest": candidate.digest,
                }
            failed_stage = "homepage_import"
            homepage_import_report = dependencies.run_homepage_importer(
                release=release,
                env=env,
                run=run,
                run_id=run_id,
                mongo_uri=target.mongo_uri,
                media_image_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
            refs["homepageImportReportRef"] = (
                (run / "homepage-import.json")
                .relative_to(dependencies.output_root)
                .as_posix()
            )
            failed_stage = "coverage_receipt"
            coverage_receipt = dependencies.write_environment_coverage_receipt(
                environment=target.environment,
                release_id=release_id,
                run_id=run_id,
                release_root=release,
                run_root=run,
                importer_report=homepage_import_report,
                api_base_url=target.api_base_url,
            )
            refs["coverageReceiptRef"] = coverage_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            expected_entities = contract.get("desiredRefs", {}).get("entities", [])
            if not args.dry_run and expected_entities:
                failed_stage = "homepage_verification_cases"
                try:
                    verification_cases = (
                        dependencies.write_homepage_verification_case_manifest(
                            environment=target.environment,
                            release_root=release,
                            run_root=run,
                            run_id=run_id,
                            importer_report=homepage_import_report,
                        )
                    )
                except HomepageVerificationCaseError as exc:
                    raise SystemExit(
                        f"[ship] homepage verification case manifest failed: {exc}"
                    ) from exc
                refs["homepageVerificationCasesRef"] = verification_cases.relative_to(
                    dependencies.output_root
                ).as_posix()
        failed_stage = "terminal_result"
        _write_terminal_result(
            dependencies=dependencies,
            run=run,
            document={
                **base_result,
                "status": ReleaseRunStatus.DRY_RUN
                if args.dry_run
                else ReleaseRunStatus.PREPARED,
                **refs,
                **candidate_evidence,
            },
        )
    except (Exception, SystemExit) as error:
        receipt_error = _record_failed_result(
            dependencies=dependencies,
            run=run,
            base_result=base_result,
            failed_stage=failed_stage,
            error=error,
        )
        _failed_receipt_note(error=error, receipt_error=receipt_error)
        raise
    print(f"[ship] {env} release={release_id} run={run_id} evidence={run}")


def activate_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    admission = _release_admission(args, dependencies)
    release_id = validate_path_segment(admission.release_id, label="release_id")
    env = str(args.env).strip()
    target = dependencies.resolve_environment_release_target(env)
    dependencies.assert_environment_release_policy(
        release=admission.release,
        contract=admission.contract,
        environment=env,
    )
    dependencies.assert_target_action_allowed(
        target=target,
        import_to_db=True,
        dry_run=False,
        action="activate",
    )
    if env == DeploymentEnvironment.PROD and not args.confirm_prod_apply:
        raise SystemExit("[ship] prod activate 需要 --confirm-prod-apply")
    import_run_id = validate_path_segment(
        str(args.import_run_id), label="import_run_id"
    )
    import_run = dependencies.run_root(env, release_id, import_run_id)
    import_result = read_environment_result(
        import_run / "result.json",
        expected={
            "environment": env,
            "releaseId": release_id,
            "runId": import_run_id,
            "manifestDigest": admission.manifest_digest,
            **admission.result_envelope(),
        },
        required_status=ReleaseRunStatus.PREPARED,
        label="prepared apply predecessor result",
    )
    candidate_ref = str(import_result.get("contentCandidateReceiptRef") or "")
    candidate_digest = str(import_result.get("contentCandidateReceiptDigest") or "")
    if not candidate_ref or not candidate_digest:
        raise SystemExit("[ship] prepared apply result lacks Content candidate proof")
    candidate_path = dependencies.output_root / candidate_ref
    candidate = _required_adapter(
        dependencies, "load_content_release_candidate_receipt"
    )(
        candidate_path,
        output_root=dependencies.output_root,
        environment=env,
        release_id=release_id,
        manifest_digest=admission.manifest_digest,
        expected_digest=candidate_digest,
    )
    run_id = validate_path_segment(
        str(args.run_id or f"activate-{dependencies.now_compact()}"), label="run_id"
    )
    run = dependencies.create_run(env, release_id, run_id, kind=ReleaseRunKind.ACTIVATE)
    base_result: dict[str, object] = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        **_lifecycle_evidence(admission),
        **admission.result_envelope(),
        "runId": run_id,
        "importRunId": import_run_id,
        "contentCandidateReceiptRef": candidate.ref,
        "contentCandidateReceiptDigest": candidate.digest,
    }
    failed_stage = "owner_local_staging_admission"
    try:
        _require_owner_local_staging_admission(
            dependencies=dependencies,
            release=admission.release,
            contract=admission.contract,
            environment=env,
            action="activate",
        )
        failed_stage = "content_active_pre_query"
        pre = _required_adapter(dependencies, "query_content_active_release")(
            env=env,
            mongo_uri=target.mongo_uri,
            report_path=run / "content-active-pre-receipt.json",
            output_root=dependencies.output_root,
        )
        failed_stage = "content_activation_cas"
        activation = _required_adapter(dependencies, "activate_content_release")(
            env=env,
            mongo_uri=target.mongo_uri,
            release_id=release_id,
            manifest_digest=admission.manifest_digest,
            expected_active=pre.document,
            report_path=run / "content-activation-receipt.json",
            output_root=dependencies.output_root,
        )
        failed_stage = "content_active_post_query"
        post = _required_adapter(dependencies, "query_content_active_release")(
            env=env,
            mongo_uri=target.mongo_uri,
            report_path=run / "content-active-post-receipt.json",
            output_root=dependencies.output_root,
        )
        active = activation.document["active"]
        expected_revision = int(pre.document.get("revision") or 0) + 1
        if (
            post.document.get("status") != "found"
            or post.document.get("releaseId") != release_id
            or post.document.get("manifestDigest") != admission.manifest_digest
            or post.document.get("releaseClass") != active.get("releaseClass")
            or post.document.get("projectionVersion") != active.get("projectionVersion")
            or post.document.get("revision") != active.get("revision")
            or post.document.get("activatedAt") != active.get("activatedAt")
            or active.get("revision") != expected_revision
        ):
            raise SystemExit("[ship] Content activation post-CAS readback differs")
        for evidence in (candidate, pre, activation, post):
            assert_content_release_evidence_unchanged(evidence)
        completed = {
            **base_result,
            "status": ReleaseRunStatus.COMPLETED,
            "contentPreActiveReceiptRef": pre.ref,
            "contentPreActiveReceiptDigest": pre.digest,
            "contentActivationReceiptRef": activation.ref,
            "contentActivationReceiptDigest": activation.digest,
            "contentPostActiveReceiptRef": post.ref,
            "contentPostActiveReceiptDigest": post.digest,
        }
        # Never seal completed before its activation marker exists. If the marker
        # write fails, the catch path can still seal one failed result instead.
        failed_stage = "applied_ref"
        dependencies.write_applied_ref(run=run, env=env, release_id=release_id)
        failed_stage = "terminal_result"
        _write_terminal_result(dependencies=dependencies, run=run, document=completed)
    except (Exception, SystemExit) as error:
        receipt_error = _record_failed_result(
            dependencies=dependencies,
            run=run,
            base_result=base_result,
            failed_stage=failed_stage,
            error=error,
        )
        _failed_receipt_note(error=error, receipt_error=receipt_error)
        raise
    print(f"[ship] activate env={env} release={release_id} run={run_id}")


def rollback_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    admission = _release_admission(args, dependencies)
    target_id = validate_path_segment(admission.release_id, label="release_id")
    source_id = validate_path_segment(
        str(args.from_release_id), label="from_release_id"
    )
    source_manifest_digest = str(
        getattr(args, "from_manifest_digest", "") or ""
    ).strip()
    if source_id == target_id:
        raise SystemExit("[ship] rollback requires a distinct --from-release-id")
    if not source_manifest_digest:
        raise SystemExit("[ship] rollback requires --from-manifest-digest")
    release, contract = admission.release, admission.contract
    lifecycle_evidence = _lifecycle_evidence(admission)
    env = str(args.env)
    dependencies.assert_environment_release_policy(
        release=release, contract=contract, environment=env
    )
    target = dependencies.resolve_environment_release_target(env)
    if (
        env == DeploymentEnvironment.PROD
        and args.import_to_db
        and not args.dry_run
        and not args.confirm_prod_apply
    ):
        raise SystemExit("[ship] prod rollback 需要 --confirm-prod-apply")
    preflight = scan_release_contract(contract, release_root=release, phase="preflight")
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] rollback target release consistency failed")
    dependencies.assert_target_action_allowed(
        target=target,
        import_to_db=bool(args.import_to_db),
        dry_run=bool(args.dry_run),
        action="rollback",
    )
    run_id = validate_path_segment(
        str(args.run_id or f"rollback-{dependencies.now_compact()}"), label="run_id"
    )
    run = dependencies.create_run(env, target_id, run_id, kind=ReleaseRunKind.ROLLBACK)
    base_result: dict[str, object] = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": target_id,
        **lifecycle_evidence,
        **admission.result_envelope(),
        "runId": run_id,
    }
    refs = _import_evidence_refs(run, dependencies)
    failed_stage = "rollback_intent"
    try:
        dependencies.write_release_evidence(
            run / "rollback_ref.json",
            {
                "schema": "quwoquan_data.rollback_release_ref",
                "authority": "asserted_intent",
                "rollbackTo": target_id,
                "rollbackFromReleaseId": source_id,
                "rollbackFromManifestDigest": source_manifest_digest,
                "rollbackToManifestDigest": admission.manifest_digest,
                "releaseRef": release_ref(target_id),
            },
            "rollback_release_ref",
        )
        if args.import_to_db and not args.dry_run:
            failed_stage = "owner_local_staging_admission"
            _require_owner_local_staging_admission(
                dependencies=dependencies,
                release=release,
                contract=contract,
                environment=env,
                action="rollback",
            )
            failed_stage = "environment_readiness"
            dependencies.require_environment_readiness(
                environment=target.environment,
                phase=ShipReadinessPhase.IMPORT,
                run=run,
                release_id=target_id,
                manifest_digest=admission.manifest_digest,
            )
        failed_stage = "consistency_preflight_evidence"
        write_json(run / "consistency-preflight.json", preflight)
        if (
            target.media_sync_root is not None
            and args.import_to_db
            and not args.dry_run
        ):
            failed_stage = "media_sync"
            dependencies.sync_media(
                release=release, destination=str(target.media_sync_root), run=run
            )
        completion_evidence: dict[str, object] = {}
        if args.import_to_db:
            failed_stage = "tag_import"
            tag_receipt = dependencies.run_tag_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                dry_run=bool(args.dry_run),
            )
            refs["tagImportReportRef"] = tag_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            failed_stage = "creator_import"
            creator_receipt = dependencies.run_creator_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                postgres_dsn=target.user_postgres_dsn,
                media_avatar_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC,
            )
            refs["creatorImportReportRef"] = creator_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            failed_stage = "content_candidate_stage"
            content_receipt = dependencies.run_content_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                media_avatar_base_url=target.media_delivery_base_url,
                media_image_base_url=target.media_delivery_base_url,
                media_video_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC,
                delete_policy=DeletePolicy.TOMBSTONE,
                creator_receipt=creator_receipt,
            )
            refs["contentImportReportRef"] = content_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            if not args.dry_run:
                failed_stage = "content_candidate_query"
                candidate = _required_adapter(
                    dependencies, "query_content_release_candidate"
                )(
                    env=env,
                    mongo_uri=target.mongo_uri,
                    release_id=target_id,
                    manifest_digest=admission.manifest_digest,
                    report_path=run / "content-candidate-receipt.json",
                    output_root=dependencies.output_root,
                )
                # Query after staging: this exact receipt, not operator input, is CAS authority.
                failed_stage = "content_active_pre_query"
                pre = _required_adapter(dependencies, "query_content_active_release")(
                    env=env,
                    mongo_uri=target.mongo_uri,
                    report_path=run / "content-active-pre-receipt.json",
                    output_root=dependencies.output_root,
                )
                if (
                    pre.document.get("status") != "found"
                    or pre.document.get("releaseId") != source_id
                    or pre.document.get("manifestDigest") != source_manifest_digest
                ):
                    raise SystemExit(
                        "CONTENT.RELEASE.ACTIVE_CAS_CONFLICT: rollback asserted intent differs from queried active pointer"
                    )
                failed_stage = "content_activation_cas"
                activation = _required_adapter(
                    dependencies, "activate_content_release"
                )(
                    env=env,
                    mongo_uri=target.mongo_uri,
                    release_id=target_id,
                    manifest_digest=admission.manifest_digest,
                    expected_active=pre.document,
                    report_path=run / "content-activation-receipt.json",
                    output_root=dependencies.output_root,
                )
                failed_stage = "content_active_post_query"
                post = _required_adapter(dependencies, "query_content_active_release")(
                    env=env,
                    mongo_uri=target.mongo_uri,
                    report_path=run / "content-active-post-receipt.json",
                    output_root=dependencies.output_root,
                )
                active = activation.document["active"]
                if (
                    post.document.get("status") != "found"
                    or post.document.get("releaseId") != target_id
                    or post.document.get("manifestDigest") != admission.manifest_digest
                    or post.document.get("releaseClass") != active.get("releaseClass")
                    or post.document.get("projectionVersion")
                    != active.get("projectionVersion")
                    or post.document.get("revision") != active.get("revision")
                    or post.document.get("activatedAt") != active.get("activatedAt")
                    or active.get("revision") != int(pre.document["revision"]) + 1
                ):
                    raise SystemExit(
                        "[ship] Content rollback post-CAS readback differs"
                    )
                for evidence in (candidate, pre, activation, post):
                    assert_content_release_evidence_unchanged(evidence)
                completion_evidence = {
                    "contentCandidateReceiptRef": candidate.ref,
                    "contentCandidateReceiptDigest": candidate.digest,
                    "contentPreActiveReceiptRef": pre.ref,
                    "contentPreActiveReceiptDigest": pre.digest,
                    "contentActivationReceiptRef": activation.ref,
                    "contentActivationReceiptDigest": activation.digest,
                    "contentPostActiveReceiptRef": post.ref,
                    "contentPostActiveReceiptDigest": post.digest,
                }
            failed_stage = "homepage_import"
            homepage_import_report = dependencies.run_homepage_importer(
                release=release,
                env=env,
                run=run,
                run_id=run_id,
                mongo_uri=target.mongo_uri,
                media_image_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC,
            )
            refs["homepageImportReportRef"] = (
                (run / "homepage-import.json")
                .relative_to(dependencies.output_root)
                .as_posix()
            )
            failed_stage = "coverage_receipt"
            coverage_receipt = dependencies.write_environment_coverage_receipt(
                environment=target.environment,
                release_id=target_id,
                run_id=run_id,
                release_root=release,
                run_root=run,
                importer_report=homepage_import_report,
                api_base_url=target.api_base_url,
            )
            refs["coverageReceiptRef"] = coverage_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            expected_entities = contract.get("desiredRefs", {}).get("entities", [])
            if not args.dry_run and expected_entities:
                failed_stage = "homepage_verification_cases"
                try:
                    verification_cases = (
                        dependencies.write_homepage_verification_case_manifest(
                            environment=target.environment,
                            release_root=release,
                            run_root=run,
                            run_id=run_id,
                            importer_report=homepage_import_report,
                        )
                    )
                except HomepageVerificationCaseError as exc:
                    raise SystemExit(
                        f"[ship] homepage verification case manifest failed: {exc}"
                    ) from exc
                refs["homepageVerificationCasesRef"] = verification_cases.relative_to(
                    dependencies.output_root
                ).as_posix()
        failed_stage = "terminal_result"
        result = {
            **base_result,
            "status": ReleaseRunStatus.DRY_RUN
            if args.dry_run
            else (
                ReleaseRunStatus.COMPLETED
                if args.import_to_db
                else ReleaseRunStatus.PREPARED
            ),
            **refs,
            **completion_evidence,
        }
        if args.import_to_db and not args.dry_run:
            # The marker must precede completed so result.json can never overclaim.
            failed_stage = "applied_ref"
            dependencies.write_applied_ref(run=run, env=env, release_id=target_id)
        failed_stage = "terminal_result"
        _write_terminal_result(dependencies=dependencies, run=run, document=result)
    except (Exception, SystemExit) as error:
        receipt_error = _record_failed_result(
            dependencies=dependencies,
            run=run,
            base_result=base_result,
            failed_stage=failed_stage,
            error=error,
        )
        _failed_receipt_note(error=error, receipt_error=receipt_error)
        raise
    print(f"[ship] rollback env={env} target={target_id} run={run_id}")


def verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    from content.release.environment._ship_consumer_verification import (
        verify_release_consumers as verify_consumers,
    )

    verify_consumers(args, dependencies=dependencies)
