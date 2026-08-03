"""Consumer API verification for one immutable environment release."""
from __future__ import annotations

import argparse
from pathlib import Path

from content.release.environment._ship_operation_dependencies import (
    ShipOperationDependencies,
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
from content.release.environment.topology import EnvironmentReleaseMode
from content.release.model import ReleaseKind
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import read_json
from core.release_layout import payload_digest, payload_file


def verify_release_consumers(
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
            f"[ship] {env} is projection-only and has no imported homepage API to verify"
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

    def record_failure(stage: str, error: Exception) -> None:
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
                "error": str(error),
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
    if readiness_phase not in {"research", "consumer", "commercial"}:
        raise SystemExit(
            "[ship] --readiness-phase must be research, consumer or commercial"
        )
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
            f"[ship] homepage verification cases missing from import run: {case_manifest}"
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
