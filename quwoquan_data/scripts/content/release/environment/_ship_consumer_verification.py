"""Consumer API verification for one immutable environment release."""
from __future__ import annotations

import argparse
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment._ship_operation_dependencies import (
    ShipOperationDependencies,
)
from content.release.environment.importers import assert_import_report_contract
from content.release.environment.activation_recovery import (
    ContentDeliveryRecoveryError,
    PreviousVerifiedRelease,
    restore_after_delivery_failure,
)
from content.release.environment.baseline_api_verification import (
    BaselineApiVerificationError,
)
from content.release.environment.homepage_api_verification import (
    HomepageApiVerificationError,
)
from content.release.environment.post_api_verification import PostApiVerificationError
from content.release.environment.readiness import ShipReadinessPhase
from content.release.environment.release_readiness import (
    EnvironmentReleaseReadinessError,
)
from content.release.environment.research_isolation_verification import (
    ResearchIsolationVerificationError,
)
from content.release.environment.topology import EnvironmentReleaseMode
from content.release.model import DeletePolicy, ImportMode, ReleaseKind
from core.control_types import ContentImportPhase, ReleaseRunKind, ReleaseRunStatus
from core.io import read_json
from core.release_layout import payload_digest, payload_file
from verify.release_publishability import readiness_phase_issue

_SENSITIVE_RECEIPT_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|access[_-]?token|refresh[_-]?token|token|password|"
    r"secret|body|query)\b\s*[:=]\s*(?:Bearer\s+)?(?:\{[^}]*\}|\[[^]]*\]|"
    r'"[^"]*"|\'[^\']*\'|[^\s,;]+)'
)
_SENSITIVE_RECEIPT_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")


class ConsumerVerificationFailed(SystemExit):
    """A real consumer verifier ran against the active release and failed.

    Only this failure may trigger a restore. Argument errors, missing evidence
    files or projection-only environments exit before any verifier runs and
    must never roll a genuinely activated release back.
    """


def _failure_receipt_error(error: Exception) -> str:
    """Keep one bounded diagnostic line without persisting request secrets."""

    message = " ".join(str(error).splitlines()).strip()
    message = _SENSITIVE_RECEIPT_BEARER.sub("Bearer [REDACTED]", message)
    message = _SENSITIVE_RECEIPT_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        message,
    )
    return (message or "verification failed")[:1024]


def _failure_receipt_evidence(error: Exception) -> dict[str, Any]:
    """Retain bounded typed attempt evidence exposed by a verifier blocker."""

    attempts = getattr(error, "operation_attempts", ())
    if not isinstance(attempts, (list, tuple)) or not attempts:
        return {}
    rows = [dict(row) for row in attempts[:2] if isinstance(row, Mapping)]
    return {"operationAttempts": rows} if rows else {}


def _verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    release_id = str(args.release_id).strip()
    release, contract = dependencies.load_release(release_id)
    env = str(args.env).strip()
    target = dependencies.resolve_environment_release_target(env)
    if target.mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        raise SystemExit(
            f"[ship] {env} is projection-only and has no imported homepage API "
            "to verify"
        )
    if not target.api_base_url:
        raise SystemExit(f"[ship] {env} topology does not declare an API base URL")
    import_run = dependencies.run_root(
        env,
        release_id,
        str(args.import_run_id).strip(),
    )
    import_result = read_json(import_run / "result.json")
    if (
        import_result.get("environment") != env
        or import_result.get("status") != ReleaseRunStatus.COMPLETED
    ):
        raise SystemExit("[ship] import run is not a completed environment release")
    if import_result.get("contentPhase") not in (None, ContentImportPhase.ACTIVATE.value):
        raise SystemExit(
            "[ship] consumer verification reads active surfaces; the import run "
            f"is still {import_result.get('contentPhase')} — run ship activate first"
        )
    header = read_json(payload_file(release, "release.json"))
    lifecycle_evidence = {
        "releaseClass": str(header.get("releaseClass") or ""),
        "productLifecycleState": str(
            header.get("productLifecycleState") or ""
        ),
        "containsUnverifiedAssets": bool(
            header.get("containsUnverifiedAssets")
        ),
        "manifestDigest": payload_digest(release),
    }
    try:
        release_kind = ReleaseKind(str(header.get("releaseKind") or ""))
    except ValueError as exc:
        raise SystemExit("[ship] releaseKind is invalid") from exc
    run_id = str(args.run_id or f"consumer-api-{dependencies.now_compact()}")
    run = dependencies.create_run(
        env,
        release_id,
        run_id,
        kind=ReleaseRunKind.VERIFY,
    )

    def record_failure(
        stage: str,
        error: Exception,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        failure_evidence = _failure_receipt_evidence(error)
        dependencies.write_verification_result(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                **lifecycle_evidence,
                "runId": run_id,
                "importRunId": str(args.import_run_id).strip(),
                "status": ReleaseRunStatus.FAILED,
                "failedStage": stage,
                "error": _failure_receipt_error(error),
                **failure_evidence,
                **dict(evidence or {}),
            },
        )

    try:
        tag_report = dependencies.write_tag_consumer_verification(
            environment=env,
            release_id=release_id,
            release_kind=release_kind,
            run_id=run_id,
            release_contract=contract,
            import_report_path=import_run / "tag-import.json",
            output_path=run / "tag-consumer-verification.json",
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        record_failure("tag_consumer_verification", exc)
        raise ConsumerVerificationFailed(
            f"[ship] {env} tag consumer verification failed: {exc}"
        ) from exc

    if release_kind is ReleaseKind.EMPTY_BASELINE:
        if import_result.get("homepageVerificationCasesRef"):
            raise SystemExit(
                "[ship] empty baseline import must not bind positive homepage cases"
            )
        try:
            report = dependencies.write_baseline_api_verification(
                environment=target.environment,
                release_id=release_id,
                run_id=run_id,
                importer_report_path=import_run / "homepage-import.json",
                output_path=run / "baseline-api-verification.json",
                api_base_url=target.api_base_url,
                ssl_cafile=target.ssl_cafile,
            )
        except BaselineApiVerificationError as exc:
            record_failure("baseline_api_verification", exc)
            raise ConsumerVerificationFailed(
                f"[ship] {env} baseline API verification failed: {exc}"
            ) from exc
        dependencies.write_verification_result(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                **lifecycle_evidence,
                "runId": run_id,
                "importRunId": str(args.import_run_id).strip(),
                "status": ReleaseRunStatus.COMPLETED,
                "tagConsumerVerificationRef": tag_report.relative_to(
                    dependencies.output_root
                ).as_posix(),
                "baselineApiVerificationRef": report.relative_to(
                    dependencies.output_root
                ).as_posix(),
            },
        )
        print(
            f"[ship] {env} baseline API release={release_id} "
            f"run={run_id} evidence={run}"
        )
        return
    readiness_phase = str(
        getattr(args, "readiness_phase", "commercial") or "commercial"
    ).strip()
    phase_issue = readiness_phase_issue(readiness_phase)
    if phase_issue is not None:
        raise SystemExit(f"[ship] --readiness-phase: {phase_issue}")
    lifecycle_exit_ref = str(
        getattr(args, "lifecycle_exit_ref", "") or ""
    ).strip()
    if readiness_phase == "commercial" and not lifecycle_exit_ref:
        raise SystemExit(
            f"[ship] GATE_BLOCK {env}/commercial: lifecycleExitRef is required"
        )
    research_isolation_report: Path | None = None
    if readiness_phase == "research":
        try:
            research_isolation_report = (
                dependencies.write_research_isolation_verification(
                    environment=env,
                    release_id=release_id,
                    verify_run_id=run_id,
                    release_root=release,
                    output_root=dependencies.output_root,
                    output_path=(
                        run / "research-isolation-verification.json"
                    ),
                    runtime_proof_path=(
                        run / "research-isolation-runtime-proof.json"
                    ),
                )
            )
            isolation = read_json(research_isolation_report)
        except (
            ResearchIsolationVerificationError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            record_failure("research_isolation_verification", exc)
            raise ConsumerVerificationFailed(
                f"[ship] {env} research isolation verification failed: {exc}"
            ) from exc
        if isolation.get("outcome") != "PASS":
            blocker = isolation.get("blocker")
            code = (
                str(blocker.get("code") or "DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE")
                if isinstance(blocker, dict)
                else "DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE"
            )
            error = ResearchIsolationVerificationError(
                f"{code}: GATE_BLOCK research runtime isolation proof is unavailable"
            )
            isolation_ref = research_isolation_report.relative_to(
                dependencies.output_root
            ).as_posix()
            record_failure(
                "research_isolation_verification",
                error,
                evidence={"researchIsolationVerificationRef": isolation_ref},
            )
            raise ConsumerVerificationFailed(f"[ship] {env} {error}")
    post_report: Path | None = None
    if dependencies.release_has_posts(contract):
        try:
            post_report = dependencies.write_post_api_verification(
                environment=target.environment,
                release_id=release.name,
                run_id=run_id,
                release_root=release,
                importer_report_path=import_run / "import.json",
                creator_importer_report_path=import_run / "creator-import.json",
                output_path=run / "post-api-verification.json",
                api_base_url=target.api_base_url,
                media_delivery_base_url=target.media_delivery_base_url,
                ssl_cafile=target.ssl_cafile,
                readiness_phase=readiness_phase,
            )
        except PostApiVerificationError as exc:
            record_failure("post_api_verification", exc)
            raise ConsumerVerificationFailed(
                f"[ship] {env} post API verification failed: {exc}"
            ) from exc
    case_manifest = import_run / "homepage_verification_cases.json"
    if not case_manifest.is_file():
        raise SystemExit(
            "[ship] homepage verification cases missing from import run: "
            f"{case_manifest}"
        )
    if (
        import_result.get("homepageVerificationCasesRef")
        != case_manifest.relative_to(dependencies.output_root).as_posix()
    ):
        raise SystemExit(
            "[ship] import run does not bind a completed homepage verification "
            "case manifest"
        )
    try:
        homepage_report = dependencies.write_homepage_api_verification(
            environment=target.environment,
            release_id=release.name,
            run_id=run_id,
            case_manifest_path=case_manifest,
            output_path=run / "homepage-api-verification.json",
            api_base_url=target.api_base_url,
            ssl_cafile=target.ssl_cafile,
        )
    except HomepageApiVerificationError as exc:
        record_failure("homepage_api_verification", exc)
        raise ConsumerVerificationFailed(
            f"[ship] {env} homepage API verification failed: {exc}"
        ) from exc
    readiness_report: Path | None = None
    if post_report is not None:
        previous_readiness_ref = str(
            getattr(args, "previous_environment_readiness", "") or ""
        ).strip()
        previous_readiness_relative = Path(previous_readiness_ref)
        if previous_readiness_ref and (
            previous_readiness_relative.is_absolute()
            or ".." in previous_readiness_relative.parts
        ):
            raise SystemExit(
                "[ship] previous environment readiness must be a safe output-relative ref"
            )
        previous_readiness_path = (
            dependencies.output_root / previous_readiness_relative
            if previous_readiness_ref
            else None
        )
        try:
            readiness_report = dependencies.write_environment_release_readiness(
                environment=env,
                release_id=release_id,
                import_run_id=str(args.import_run_id).strip(),
                verify_run_id=run_id,
                release_root=release,
                import_report_path=import_run / "import.json",
                creator_import_report_path=import_run / "creator-import.json",
                tag_consumer_verification_path=tag_report,
                homepage_api_verification_path=homepage_report,
                post_api_verification_path=post_report,
                research_isolation_verification_path=(
                    research_isolation_report
                ),
                previous_environment_readiness_path=previous_readiness_path,
                output_root=dependencies.output_root,
                output_path=run / "release-readiness.json",
                readiness_phase=readiness_phase,
            )
        except EnvironmentReleaseReadinessError as exc:
            record_failure("environment_release_readiness", exc)
            raise ConsumerVerificationFailed(
                f"[ship] {env} environment release readiness failed: {exc}"
            ) from exc
    if readiness_report is not None:
        try:
            dependencies.require_environment_readiness(
                environment=target.environment,
                phase=ShipReadinessPhase(readiness_phase),
                run=run,
                release_id=release_id,
                verify_run_id=run_id,
                manifest_digest=payload_digest(release),
                lifecycle_exit_ref=lifecycle_exit_ref,
            )
        except SystemExit as exc:
            readiness_error = RuntimeError(str(exc))
            record_failure("environment_readiness", readiness_error)
            raise ConsumerVerificationFailed(str(exc)) from exc
    result = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        **lifecycle_evidence,
        "runId": run_id,
        "importRunId": str(args.import_run_id).strip(),
        "readinessPhase": readiness_phase,
        "status": ReleaseRunStatus.COMPLETED,
        "tagConsumerVerificationRef": tag_report.relative_to(
            dependencies.output_root
        ).as_posix(),
        "homepageApiVerificationRef": homepage_report.relative_to(
            dependencies.output_root
        ).as_posix(),
    }
    if lifecycle_exit_ref:
        result["lifecycleExitRef"] = lifecycle_exit_ref
    if research_isolation_report is not None:
        result["researchIsolationVerificationRef"] = (
            research_isolation_report.relative_to(
                dependencies.output_root
            ).as_posix()
        )
    if post_report is not None:
        result["postApiVerificationRef"] = post_report.relative_to(
            dependencies.output_root
        ).as_posix()
    if readiness_report is not None:
        result["releaseReadinessRef"] = readiness_report.relative_to(
            dependencies.output_root
        ).as_posix()
    dependencies.write_verification_result(run / "result.json", result)
    print(
        f"[ship] {env} consumer API release={release_id} "
        f"run={run_id} evidence={run}"
    )


def verify_release_candidate(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    """Pre-activation verification bound to the staged candidate identity.

    Nothing here touches live consumer surfaces: the candidate is read back
    from ``posts_candidate`` by ``candidateRevision`` and compared with the
    immutable release closure. Failure leaves pointer, ``posts`` and media
    untouched, so there is nothing to restore.
    """

    release_id = str(args.release_id).strip()
    release, _contract = dependencies.load_release(release_id)
    env = str(args.env).strip()
    target = dependencies.resolve_environment_release_target(env)
    import_run_id = str(args.import_run_id).strip()
    import_run = dependencies.run_root(env, release_id, import_run_id)
    import_result = read_json(import_run / "result.json")
    manifest_digest = payload_digest(release)
    if (
        import_result.get("environment") != env
        or import_result.get("releaseId") != release_id
        or import_result.get("manifestDigest") != manifest_digest
        or import_result.get("status") != ReleaseRunStatus.COMPLETED
        or import_result.get("contentPhase") != ContentImportPhase.STAGE.value
        or int(import_result.get("candidateRevision") or 0) <= 0
    ):
        raise SystemExit(
            f"[ship] import run {import_run_id} is not a completed stage run for "
            f"{release_id}@{manifest_digest}"
        )
    candidate_revision = int(import_result["candidateRevision"])
    full_sync = bool(import_result.get("fullSync"))
    header = read_json(payload_file(release, "release.json"))
    lifecycle_evidence = {
        "releaseClass": str(header.get("releaseClass") or ""),
        "productLifecycleState": str(header.get("productLifecycleState") or ""),
        "containsUnverifiedAssets": bool(header.get("containsUnverifiedAssets")),
        "manifestDigest": manifest_digest,
    }
    run_id = str(getattr(args, "run_id", "") or f"candidate-{dependencies.now_compact()}")
    run = dependencies.create_run(env, release_id, run_id, kind=ReleaseRunKind.VERIFY)
    base = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        **lifecycle_evidence,
        "runId": run_id,
        "importRunId": import_run_id,
        "contentPhase": ContentImportPhase.VERIFY.value,
        "candidateRevision": candidate_revision,
    }
    try:
        stage_report = assert_import_report_contract(
            import_run / "import.json",
            expected_release_id=release_id,
            expected_manifest_digest=manifest_digest,
        )
        if int(stage_report.get("candidateRevision") or 0) != candidate_revision:
            raise RuntimeError("stage report candidateRevision drifts from the run result")
        media_sync_path = import_run / "media-sync.json"
        if media_sync_path.is_file():
            # 媒体字节/摘要在 additive copy 时逐文件按 manifest sha256 校验；这里只
            # 复核该证据成立，不在激活前签发任何可消费 URL。
            media_sync = read_json(media_sync_path)
            if media_sync.get("failed") or media_sync.get("issues"):
                raise RuntimeError("stage media sync evidence records failures")
            if int(media_sync.get("pruned") or 0) != 0:
                raise RuntimeError("stage media sync must be additive; pruning is post-activate only")
        readback = dependencies.run_content_importer(
            release=release, env=env, run=run, mongo_uri=target.mongo_uri,
            media_avatar_base_url=target.media_delivery_base_url,
            media_image_base_url=target.media_delivery_base_url,
            media_video_base_url=target.media_delivery_base_url,
            dry_run=False, creator_receipt=import_run / "creator-import.json",
            phase=ContentImportPhase.VERIFY, candidate_revision=candidate_revision,
            mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            delete_policy=DeletePolicy.TOMBSTONE if full_sync else DeletePolicy.NONE,
        )
        staged_post_ids = sorted(
            str(row.get("postId") or "") for row in stage_report.get("postBindings") or []
        )
        if sorted(readback.get("candidatePostIds") or []) != staged_post_ids:
            raise RuntimeError("candidate readback postIds drift from the staged closure")
    except (OSError, TypeError, ValueError, RuntimeError, SystemExit) as exc:
        dependencies.write_verification_result(
            run / "result.json",
            {
                **base,
                "status": ReleaseRunStatus.FAILED,
                "failedStage": "candidate_readback",
                "error": _failure_receipt_error(
                    exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                ),
            },
        )
        raise SystemExit(f"[ship] {env} candidate verification failed: {exc}") from exc
    dependencies.write_verification_result(
        run / "result.json",
        {
            **base,
            "status": ReleaseRunStatus.COMPLETED,
            "candidateVerificationRef": (
                run / "candidate-verify.json"
            ).relative_to(dependencies.output_root).as_posix(),
        },
    )
    print(
        f"[ship] {env} candidate verified release={release_id} "
        f"candidateRevision={candidate_revision} run={run_id} evidence={run}"
    )


def verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    """Verify the run's phase: candidate readback before activate, consumer readback after.

    Only the post-activate path may restore a verified previous release; a
    failed candidate verification has changed nothing that needs restoring.
    """

    env = str(getattr(args, "env", "") or "").strip()
    release_id = str(getattr(args, "release_id", "") or "").strip()
    import_run_id = str(getattr(args, "import_run_id", "") or "").strip()
    import_result_path = dependencies.run_root(env, release_id, import_run_id) / "result.json"
    if import_result_path.is_file() and (
        read_json(import_result_path).get("contentPhase")
        == ContentImportPhase.STAGE.value
    ):
        verify_release_candidate(args, dependencies=dependencies)
        return
    try:
        _verify_release_consumers(args, dependencies=dependencies)
    except ConsumerVerificationFailed as original:
        # 只有 verifier 真实失败才进入 restore；参数错误、证据缺失等 SystemExit
        # 直接冒泡，不得在 alpha/beta/gamma 上把敲错参数变成一次真实回滚。
        environment = str(getattr(args, "env", "") or "").strip()
        failed_release_id = str(
            getattr(args, "release_id", "") or ""
        ).strip()
        import_run_id = str(
            getattr(args, "import_run_id", "") or ""
        ).strip()
        restore = dependencies.restore_previous_release
        if restore is None:
            recovery_error = ContentDeliveryRecoveryError(
                "DATA.DELIVERY_RESTORE_UNAVAILABLE: formal restore callback is unavailable"
            )
            raise SystemExit(f"{original}; {recovery_error}") from original
        restored_activate_run: dict[str, str] = {}

        def replay_previous(release: PreviousVerifiedRelease) -> None:
            # fresh stage → verify → activate；返回值只用于随后的四入口读回绑定。
            restored_activate_run["runId"] = str(
                restore(
                    environment=environment,
                    failed_release_id=failed_release_id,
                    previous_release_id=release.release_id,
                    expected_revision=int(
                        assert_import_report_contract(import_report)["revision"]
                    ),
                )
                or ""
            )

        try:
            import_report = dependencies.run_root(
                environment,
                failed_release_id,
                import_run_id,
            ) / "import.json"
            previous = restore_after_delivery_failure(
                output_root=dependencies.output_root,
                environment=environment,
                failed_release_id=failed_release_id,
                import_report_path=import_report,
                replay_previous=replay_previous,
            )
        except (OSError, TypeError, ValueError, ContentDeliveryRecoveryError) as exc:
            raise SystemExit(f"{original}; {exc}") from original
        except SystemExit as exc:
            raise SystemExit(
                f"{original}; DATA.DELIVERY.ROLLBACK_FAILED: {exc}"
            ) from original
        # 回滚只有在 previous release 重新通过四入口读回后才算恢复；否则收敛为
        # rollback_failed，不得把“pointer 已切回”伪装成“服务已恢复”。
        readback_run_id = restored_activate_run.get("runId", "")
        if not readback_run_id:
            raise SystemExit(
                f"{original}; DATA.DELIVERY.ROLLBACK_FAILED: restore of "
                f"releaseId={previous.release_id} returned no activate run to read back"
            ) from original
        if readback_run_id:
            try:
                _verify_release_consumers(
                    argparse.Namespace(
                        release_id=previous.release_id,
                        env=environment,
                        import_run_id=readback_run_id,
                        run_id=f"restore-readback-{dependencies.now_compact()}",
                        readiness_phase=str(
                            getattr(args, "readiness_phase", "commercial") or "commercial"
                        ),
                        lifecycle_exit_ref=str(
                            getattr(args, "lifecycle_exit_ref", "") or ""
                        ),
                        previous_environment_readiness=str(
                            getattr(args, "previous_environment_readiness", "") or ""
                        ),
                    ),
                    dependencies=dependencies,
                )
            except SystemExit as exc:
                raise SystemExit(
                    f"{original}; DATA.DELIVERY.ROLLBACK_FAILED: restored "
                    f"releaseId={previous.release_id} failed consumer readback: {exc}"
                ) from original
        raise SystemExit(
            f"{original}; DATA.DELIVERY.PREVIOUS_RELEASE_RESTORED: "
            f"releaseId={previous.release_id}"
        ) from original
