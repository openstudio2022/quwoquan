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
from content.release.environment.activation_recovery import (
    ContentDeliveryRecoveryError,
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
from content.release.model import ReleaseKind
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import read_json
from core.release_layout import payload_digest, payload_file
from verify.release_publishability import readiness_phase_issue

_SENSITIVE_RECEIPT_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|access[_-]?token|refresh[_-]?token|token|password|"
    r"secret|body|query)\b\s*[:=]\s*(?:Bearer\s+)?(?:\{[^}]*\}|\[[^]]*\]|"
    r'"[^"]*"|\'[^\']*\'|[^\s,;]+)'
)
_SENSITIVE_RECEIPT_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")


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
        raise SystemExit(
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
            raise SystemExit(
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
            raise SystemExit(
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
            raise SystemExit(f"[ship] {env} {error}")
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
            raise SystemExit(
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
        raise SystemExit(
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
            raise SystemExit(
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
            raise
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


def verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    """Verify candidate delivery and restore a verified previous release on failure."""

    try:
        _verify_release_consumers(args, dependencies=dependencies)
    except SystemExit as original:
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
                replay_previous=lambda release: restore(
                    environment=environment,
                    failed_release_id=failed_release_id,
                    previous_release_id=release.release_id,
                ),
            )
        except (OSError, TypeError, ValueError, ContentDeliveryRecoveryError) as exc:
            raise SystemExit(f"{original}; {exc}") from original
        raise SystemExit(
            f"{original}; DATA.DELIVERY.PREVIOUS_RELEASE_RESTORED: "
            f"releaseId={previous.release_id}"
        ) from original
