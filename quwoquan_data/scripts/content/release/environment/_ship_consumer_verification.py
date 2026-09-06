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
from content.release.environment.baseline_api_verification import (
    BaselineApiVerificationError,
)
from content.release.environment.homepage_api_verification import (
    HomepageApiVerificationError,
)
from content.release.environment.importers import load_content_release_receipt
from content.release.environment.post_api_verification import PostApiVerificationError
from content.release.environment.readiness import ShipReadinessPhase
from content.release.environment.release_readiness import (
    EnvironmentReleaseReadinessError,
)
from content.release.environment.research_isolation_verification import (
    ResearchIsolationVerificationError,
)
from content.release.environment.run_evidence import (
    read_environment_result,
    validate_path_segment,
)
from content.release.environment.topology import EnvironmentReleaseMode
from content.release.model import ReleaseKind
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import read_json
from core.release_layout import payload_file
from verify.release_publishability import readiness_phase_issue

_SENSITIVE_RECEIPT_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|access[_-]?token|refresh[_-]?token|token|password|"
    r"secret|body|query)\b\s*[:=]\s*(?:Bearer\s+)?(?:\{[^}]*\}|\[[^]]*\]|"
    r'"[^"]*"|\'[^\']*\'|[^\s,;]+)'
)
_SENSITIVE_RECEIPT_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_SENSITIVE_RECEIPT_URL_CREDENTIALS = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@"
)


def _failure_receipt_error(error: Exception) -> str:
    """Keep one bounded diagnostic line without persisting request secrets."""

    message = " ".join(str(error).splitlines()).strip()
    message = _SENSITIVE_RECEIPT_BEARER.sub("Bearer [REDACTED]", message)
    message = _SENSITIVE_RECEIPT_URL_CREDENTIALS.sub(r"\1[REDACTED]@", message)
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
    admission = getattr(args, "release_admission", None)
    if admission is None:
        admission = dependencies.admit_release(args)
    if admission is None:
        raise SystemExit("[ship] GATE_BLOCK sealed release admission is missing")
    release_id = str(admission.release_id).strip()
    release, contract = admission.release, admission.contract
    env = str(args.env).strip()
    target = dependencies.resolve_environment_release_target(env)
    if target.mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        raise SystemExit(
            f"[ship] {env} is projection-only and has no imported homepage API "
            "to verify"
        )
    if not target.api_base_url:
        raise SystemExit(f"[ship] {env} topology does not declare an API base URL")
    import_run_id = validate_path_segment(
        str(args.import_run_id),
        label="import_run_id",
    )
    import_run = dependencies.run_root(env, release_id, import_run_id)
    import_result = read_environment_result(
        import_run / "result.json",
        expected={
            "environment": env,
            "runId": import_run_id,
            "releaseId": release_id,
            "manifestDigest": admission.manifest_digest,
            **admission.result_envelope(),
        },
        required_status=ReleaseRunStatus.COMPLETED,
        label="completed activation predecessor result",
    )
    apply_run_id = validate_path_segment(
        str(import_result.get("importRunId") or ""),
        label="activation import_run_id",
    )
    apply_run = dependencies.run_root(env, release_id, apply_run_id)
    content_evidence: dict[str, Any] = {}
    for ref_field, digest_field, schema in (
        (
            "contentCandidateReceiptRef",
            "contentCandidateReceiptDigest",
            "quwoquan.content_release_candidate_receipt",
        ),
        (
            "contentPreActiveReceiptRef",
            "contentPreActiveReceiptDigest",
            "quwoquan.content_release_active_receipt",
        ),
        (
            "contentActivationReceiptRef",
            "contentActivationReceiptDigest",
            "quwoquan.content_release_activation_receipt",
        ),
        (
            "contentPostActiveReceiptRef",
            "contentPostActiveReceiptDigest",
            "quwoquan.content_release_active_receipt",
        ),
    ):
        ref = str(import_result[ref_field])
        evidence = load_content_release_receipt(
            dependencies.output_root / ref,
            output_root=dependencies.output_root,
            schema=schema,
            environment=env,
            expected_digest=str(import_result[digest_field]),
        )
        content_evidence[ref_field] = evidence.document
        if schema == "quwoquan.content_release_candidate_receipt" and (
            evidence.document.get("status") != "found"
            or evidence.document.get("releaseId") != release_id
            or evidence.document.get("manifestDigest") != admission.manifest_digest
        ):
            raise SystemExit(
                "[ship] completed activation candidate proof identity differs"
            )
        if schema == "quwoquan.content_release_activation_receipt":
            target_identity = evidence.document.get("target", {})
            active_identity = evidence.document.get("active", {})
            if (
                target_identity.get("releaseId") != release_id
                or target_identity.get("manifestDigest") != admission.manifest_digest
                or active_identity.get("releaseId") != release_id
                or active_identity.get("manifestDigest") != admission.manifest_digest
            ):
                raise SystemExit("[ship] completed activation receipt identity differs")
        if ref_field == "contentPostActiveReceiptRef" and (
            evidence.document.get("status") != "found"
            or evidence.document.get("releaseId") != release_id
            or evidence.document.get("manifestDigest") != admission.manifest_digest
        ):
            raise SystemExit("[ship] completed activation post-active identity differs")
    pre_identity = content_evidence["contentPreActiveReceiptRef"]
    activation_identity = content_evidence["contentActivationReceiptRef"]
    post_identity = content_evidence["contentPostActiveReceiptRef"]
    expected_active = activation_identity.get("expectedActive", {})
    previous_active = activation_identity.get("previousActive", {})
    activated = activation_identity.get("active", {})
    pre_expected = {
        "found": pre_identity.get("status") == "found",
        "sourceOwner": "qwq_data",
        "revision": int(pre_identity.get("revision") or 0),
    }
    if pre_expected["found"]:
        pre_expected.update(
            releaseId=pre_identity.get("releaseId"),
            manifestDigest=pre_identity.get("manifestDigest"),
        )
    if (
        expected_active != pre_expected
        or previous_active != pre_expected
        or activated.get("revision") != pre_expected["revision"] + 1
        or post_identity.get("revision") != activated.get("revision")
        or post_identity.get("releaseClass") != activated.get("releaseClass")
        or post_identity.get("projectionVersion") != activated.get("projectionVersion")
        or post_identity.get("activatedAt") != activated.get("activatedAt")
    ):
        raise SystemExit(
            "[ship] completed activation revision-bearing evidence chain differs"
        )
    header = read_json(payload_file(release, "release.json"))
    lifecycle_evidence = {
        "releaseClass": str(header.get("releaseClass") or ""),
        "productLifecycleState": str(header.get("productLifecycleState") or ""),
        "containsUnverifiedAssets": bool(header.get("containsUnverifiedAssets")),
        "manifestDigest": admission.manifest_digest,
    }
    try:
        release_kind = ReleaseKind(str(header.get("releaseKind") or ""))
    except ValueError as exc:
        raise SystemExit("[ship] releaseKind is invalid") from exc
    run_id = validate_path_segment(
        str(args.run_id or f"consumer-api-{dependencies.now_compact()}"),
        label="run_id",
    )
    run = dependencies.create_run(
        env,
        release_id,
        run_id,
        kind=ReleaseRunKind.VERIFY,
    )

    base_result: dict[str, Any] = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        **lifecycle_evidence,
        **admission.result_envelope(),
        "runId": run_id,
        "importRunId": import_run_id,
        "contentCandidateReceiptRef": import_result["contentCandidateReceiptRef"],
        "contentCandidateReceiptDigest": import_result["contentCandidateReceiptDigest"],
        "contentPreActiveReceiptRef": import_result["contentPreActiveReceiptRef"],
        "contentPreActiveReceiptDigest": import_result["contentPreActiveReceiptDigest"],
        "contentActivationReceiptRef": import_result["contentActivationReceiptRef"],
        "contentActivationReceiptDigest": import_result[
            "contentActivationReceiptDigest"
        ],
        "contentPostActiveReceiptRef": import_result["contentPostActiveReceiptRef"],
        "contentPostActiveReceiptDigest": import_result[
            "contentPostActiveReceiptDigest"
        ],
    }
    failed_stage = "tag_consumer_verification"
    try:
        try:
            tag_report = dependencies.write_tag_consumer_verification(
                environment=env,
                release_id=release_id,
                release_kind=release_kind,
                run_id=run_id,
                release_contract=contract,
                import_report_path=apply_run / "tag-import.json",
                output_path=run / "tag-consumer-verification.json",
            )
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            raise SystemExit(
                f"[ship] {env} tag consumer verification failed: {exc}"
            ) from exc

        if release_kind is ReleaseKind.EMPTY_BASELINE:
            failed_stage = "empty_baseline_import_binding"
            if import_result.get("homepageVerificationCasesRef"):
                raise SystemExit(
                    "[ship] empty baseline import must not bind positive homepage cases"
                )
            failed_stage = "baseline_api_verification"
            try:
                report = dependencies.write_baseline_api_verification(
                    environment=target.environment,
                    release_id=release_id,
                    run_id=run_id,
                    importer_report_path=apply_run / "homepage-import.json",
                    output_path=run / "baseline-api-verification.json",
                    api_base_url=target.api_base_url,
                    ssl_cafile=target.ssl_cafile,
                )
            except BaselineApiVerificationError as exc:
                raise SystemExit(
                    f"[ship] {env} baseline API verification failed: {exc}"
                ) from exc
            failed_stage = "terminal_result"
            dependencies.write_verification_result(
                run / "result.json",
                {
                    **base_result,
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

        failed_stage = "readiness_phase"
        readiness_phase = str(
            getattr(args, "readiness_phase", "commercial") or "commercial"
        ).strip()
        phase_issue = readiness_phase_issue(readiness_phase)
        if phase_issue is not None:
            raise SystemExit(f"[ship] --readiness-phase: {phase_issue}")
        lifecycle_exit_ref = str(getattr(args, "lifecycle_exit_ref", "") or "").strip()
        failed_stage = "lifecycle_exit_ref"
        if readiness_phase == "commercial" and not lifecycle_exit_ref:
            raise SystemExit(
                f"[ship] GATE_BLOCK {env}/commercial: lifecycleExitRef is required"
            )

        research_isolation_report: Path | None = None
        if readiness_phase == "research":
            failed_stage = "research_isolation_verification"
            try:
                research_isolation_report = (
                    dependencies.write_research_isolation_verification(
                        environment=env,
                        release_id=release_id,
                        verify_run_id=run_id,
                        release_root=release,
                        output_root=dependencies.output_root,
                        output_path=(run / "research-isolation-verification.json"),
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
                exit_error = SystemExit(f"[ship] {env} {error}")
                exit_error.failure_evidence = {
                    "researchIsolationVerificationRef": (
                        research_isolation_report.relative_to(
                            dependencies.output_root
                        ).as_posix()
                    )
                }
                raise exit_error from error

        post_report: Path | None = None
        if dependencies.release_has_posts(contract):
            failed_stage = "post_api_verification"
            try:
                post_report = dependencies.write_post_api_verification(
                    environment=target.environment,
                    release_id=release.name,
                    run_id=run_id,
                    release_root=release,
                    importer_report_path=apply_run / "import.json",
                    creator_importer_report_path=apply_run / "creator-import.json",
                    output_path=run / "post-api-verification.json",
                    api_base_url=target.api_base_url,
                    media_delivery_base_url=target.media_delivery_base_url,
                    ssl_cafile=target.ssl_cafile,
                    readiness_phase=readiness_phase,
                )
            except PostApiVerificationError as exc:
                raise SystemExit(
                    f"[ship] {env} post API verification failed: {exc}"
                ) from exc

        failed_stage = "homepage_verification_cases"
        case_manifest = apply_run / "homepage_verification_cases.json"
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
        failed_stage = "homepage_api_verification"
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
            raise SystemExit(
                f"[ship] {env} homepage API verification failed: {exc}"
            ) from exc

        readiness_report: Path | None = None
        if post_report is not None:
            failed_stage = "previous_environment_readiness"
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
            failed_stage = "environment_release_readiness"
            try:
                readiness_report = dependencies.write_environment_release_readiness(
                    environment=env,
                    release_id=release_id,
                    import_run_id=import_run_id,
                    verify_run_id=run_id,
                    release_root=release,
                    import_report_path=apply_run / "import.json",
                    creator_import_report_path=apply_run / "creator-import.json",
                    tag_consumer_verification_path=tag_report,
                    homepage_api_verification_path=homepage_report,
                    post_api_verification_path=post_report,
                    research_isolation_verification_path=(research_isolation_report),
                    previous_environment_readiness_path=previous_readiness_path,
                    output_root=dependencies.output_root,
                    output_path=run / "release-readiness.json",
                    readiness_phase=readiness_phase,
                )
            except EnvironmentReleaseReadinessError as exc:
                raise SystemExit(
                    f"[ship] {env} environment release readiness failed: {exc}"
                ) from exc
        if readiness_report is not None:
            failed_stage = "environment_readiness"
            dependencies.require_environment_readiness(
                environment=target.environment,
                phase=ShipReadinessPhase(readiness_phase),
                run=run,
                release_id=release_id,
                verify_run_id=run_id,
                manifest_digest=admission.manifest_digest,
                lifecycle_exit_ref=lifecycle_exit_ref,
            )

        failed_stage = "terminal_result"
        result = {
            **base_result,
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
    except (Exception, SystemExit) as error:
        failure_evidence = _failure_receipt_evidence(error)
        extra_evidence = getattr(error, "failure_evidence", {})
        if isinstance(extra_evidence, Mapping):
            failure_evidence.update(dict(extra_evidence))
        try:
            dependencies.write_verification_result(
                run / "result.json",
                {
                    **base_result,
                    "status": ReleaseRunStatus.FAILED,
                    "failedStage": failed_stage,
                    "error": _failure_receipt_error(error),
                    **failure_evidence,
                },
            )
        except (Exception, SystemExit) as receipt_error:
            error.add_note(
                f"failed result evidence error: {_failure_receipt_error(receipt_error)}"
            )
        raise

    print(f"[ship] {env} consumer API release={release_id} run={run_id} evidence={run}")


def verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    """Verify one release; failures remain recorded and fail closed."""

    _verify_release_consumers(args, dependencies=dependencies)
