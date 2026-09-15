"""Consumer API verification for one immutable environment release."""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.content_release_environment._ship_operation_dependencies import (
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
from content.release.environment.readiness import ShipReadinessAction
from content.release.environment.release_readiness import (
    EnvironmentReleaseReadinessError,
)
from content.release.environment.run_evidence import (
    read_environment_result,
    validate_path_segment,
)
from content.release.environment.topology import EnvironmentReleaseMode
from content.release.model import ReleaseKind
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import read_json, write_json
from core.release_layout import payload_file
_SENSITIVE_RECEIPT_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|access[_-]?token|refresh[_-]?token|token|password|"
    r"secret|body|query)\b\s*[:=]\s*(?:Bearer\s+)?(?:\{[^}]*\}|\[[^]]*\]|"
    r'"[^"]*"|\'[^\']*\'|[^\s,;]+)'
)
_SENSITIVE_RECEIPT_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_SENSITIVE_RECEIPT_URL_CREDENTIALS = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@"
)

_CORE_DIAGNOSTIC_FEATURES = (
    "identity",
    "feed-detail",
    "search-recommendation",
    "image-video-range",
    "post-write-readback",
    "chat-write-readback",
)
_DATA_DIAGNOSTIC_FEATURES = frozenset(_CORE_DIAGNOSTIC_FEATURES[:4])


def _core_diagnostic_features(args: argparse.Namespace) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(getattr(args, "feature", ()) or ()))
    unknown = sorted(set(selected) - set(_CORE_DIAGNOSTIC_FEATURES))
    if unknown:
        raise SystemExit(f"[ship] GATE_BLOCK unknown core diagnostic features: {unknown}")
    return selected or tuple(_DATA_DIAGNOSTIC_FEATURES)


def _assert_core_diagnostic_scope(
    args: argparse.Namespace, *, target: Any
) -> tuple[str, ...]:
    selected = _core_diagnostic_features(args)
    env = str(args.env).strip()
    if env not in {"gamma", "prod"}:
        raise SystemExit("[ship] GATE_BLOCK core diagnostic only supports gamma or prod")
    if env == "gamma" and str(target.target_name) != "gamma-local":
        raise SystemExit("[ship] GATE_BLOCK gamma core diagnostic requires gamma-local")
    if env == "prod" and (
        str(target.target_name) != "prod-hosted"
        or str(getattr(args, "deployment_instance", "") or "") != "prevalidate"
        or str(getattr(args, "data_mode", "") or "") != "isolated"
    ):
        raise SystemExit(
            "[ship] GATE_BLOCK prod core diagnostic requires "
            "prod-hosted prevalidate with isolated data mode"
        )
    return selected


def _diagnostic_case_results(
    selected: tuple[str, ...], *, post_report: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    statuses = {name: "not_executed" for name in _CORE_DIAGNOSTIC_FEATURES}
    details = {name: "not selected" for name in _CORE_DIAGNOSTIC_FEATURES}
    if post_report is not None:
        creators = list(post_report.get("creators") or [])
        posts = list(post_report.get("posts") or [])
        feeds = list(post_report.get("feedQueries") or [])
        searches = list(post_report.get("searchQueries") or [])
        probes = [probe for post in posts for probe in list(post.get("mediaProbes") or [])]
        checks = {
            "identity": bool(post_report.get("guestLogin")) and bool(creators),
            "feed-detail": bool(posts) and bool(feeds),
            "search-recommendation": bool(searches)
                and any(row.get("name") == "homepage_recommend" for row in feeds),
            "image-video-range": bool(probes),
        }
        for feature in selected:
            if feature in _DATA_DIAGNOSTIC_FEATURES:
                statuses[feature] = "passed" if checks[feature] else "failed"
                details[feature] = "current Data consumer verifier evidence" if checks[feature] else "required Data consumer case is missing"
            else:
                details[feature] = "Data does not own account-bound write operation; Ops/App must execute and aggregate"
    return [
        {"feature": name, "status": statuses[name], "detail": details[name]}
        for name in _CORE_DIAGNOSTIC_FEATURES
    ]


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
    candidate_root = getattr(args, "runtime_candidate_root", None)
    if candidate_root is None:
        target = dependencies.resolve_environment_release_target(env)
    else:
        target = dependencies.resolve_environment_release_target(
            env, candidate_root=candidate_root
        )
        validator = dependencies.assert_environment_release_target_unchanged
        if validator is None:
            raise SystemExit(
                "[ship] GATE_BLOCK runtime candidate binding validator is missing"
            )
        validator(target)
    diagnostic = str(getattr(args, "verification_purpose", "formal-readiness")) == "core-diagnostic"
    diagnostic_features = (
        _assert_core_diagnostic_scope(args, target=target) if diagnostic else ()
    )
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
    apply_result = read_environment_result(
        apply_run / "result.json",
        expected={
            "environment": env,
            "runId": apply_run_id,
            "releaseId": release_id,
            "manifestDigest": admission.manifest_digest,
            **admission.result_envelope(),
        },
        required_status=ReleaseRunStatus.PREPARED,
        label="prepared apply predecessor result",
    )
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
        or post_identity.get("projectionVersion") != activated.get("projectionVersion")
        or post_identity.get("activatedAt") != activated.get("activatedAt")
    ):
        raise SystemExit(
            "[ship] completed activation revision-bearing evidence chain differs"
        )
    header = read_json(payload_file(release, "release.json"))
    lifecycle_evidence = {
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
        **{
            field: import_result[field]
            for owner in ("tag", "creator", "homepage", "content")
            for field in (
                f"{owner}CandidateReceiptRef",
                f"{owner}CandidateReceiptDigest",
                f"{owner}FencedReadbackReceiptRef",
                f"{owner}FencedReadbackReceiptDigest",
            )
        },
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
            if apply_result.get("homepageVerificationCasesRef"):
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

        lifecycle_exit_ref = str(getattr(args, "lifecycle_exit_ref", "") or "").strip()

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
                    include_premium_stream=not diagnostic,
                    validate_report=not diagnostic,
                )
            except PostApiVerificationError as exc:
                raise SystemExit(
                    f"[ship] {env} post API verification failed: {exc}"
                ) from exc

        failed_stage = "homepage_verification_cases"
        case_ref = str(apply_result.get("homepageVerificationCasesRef") or "")
        case_relative = Path(case_ref)
        expected_case_relative = (
            apply_run / "homepage_verification_cases.json"
        ).relative_to(dependencies.output_root)
        if (
            not case_ref
            or case_relative.is_absolute()
            or ".." in case_relative.parts
            or "\\" in case_ref
            or case_relative != expected_case_relative
        ):
            raise SystemExit(
                "[ship] prepared apply result does not bind the canonical "
                "output-relative homepage verification case manifest"
            )
        case_manifest = dependencies.output_root / case_relative
        if not case_manifest.is_file():
            raise SystemExit(
                "[ship] homepage verification cases missing from prepared apply run: "
                f"{case_manifest}"
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
        diagnostic_report: Path | None = None
        diagnostic_cases: list[dict[str, Any]] = []
        if diagnostic:
            failed_stage = "core_diagnostic_report"
            if post_report is None:
                raise SystemExit("[ship] core diagnostic requires release-bound post cases")
            diagnostic_payload = read_json(post_report)
            diagnostic_cases = _diagnostic_case_results(
                diagnostic_features, post_report=diagnostic_payload
            )
            missing = [
                row["feature"]
                for row in diagnostic_cases
                if row["feature"] in diagnostic_features
                and row["status"] != "passed"
                and row["feature"] in _DATA_DIAGNOSTIC_FEATURES
            ]
            diagnostic_report = run / "core-diagnostic-report.json"
            write_json(
                diagnostic_report,
                {
                    "schema": "quwoquan_data.core_diagnostic_report",
                    "environment": env,
                    "releaseId": release_id,
                    "manifestDigest": admission.manifest_digest,
                    "runId": run_id,
                    "activateRunId": import_run_id,
                    "applyRunId": apply_run_id,
                    "runtimeTarget": str(target.target_name),
                    "bindingDigest": str(target.binding_digest),
                    "bindingArtifactDigest": str(target.binding_artifact_digest),
                    "verificationPurpose": "core-diagnostic",
                    "selectedFeatures": list(diagnostic_features),
                    "nonPromotable": True,
                    "releaseEligibility": "GATE_BLOCK",
                    "readinessWritten": False,
                    "caseResults": diagnostic_cases,
                },
            )
            if missing:
                raise SystemExit(
                    f"[ship] core diagnostic required cases failed: {missing}"
                )
        if post_report is not None and not diagnostic:
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
                    previous_environment_readiness_path=previous_readiness_path,
                    output_root=dependencies.output_root,
                    output_path=run / "release-readiness.json",
                )
            except EnvironmentReleaseReadinessError as exc:
                raise SystemExit(
                    f"[ship] {env} environment release readiness failed: {exc}"
                ) from exc
        if readiness_report is not None:
            failed_stage = "environment_readiness"
            dependencies.require_environment_readiness(
                environment=target.environment,
                action=ShipReadinessAction.VERIFY,
                run=run,
                release_id=release_id,
                verify_run_id=run_id,
                manifest_digest=admission.manifest_digest,
                lifecycle_exit_ref=lifecycle_exit_ref,
            )

        failed_stage = "terminal_result"
        result = {
            **base_result,
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
