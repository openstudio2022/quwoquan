#!/usr/bin/env python3
"""Verify one immutable data release has the minimum lifecycle evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_file
from verify.release_environment_readiness import environment_release_readiness_issues
from verify.release_lifecycle_attestation import (
    RELEASE_ATTESTATION,
    read_object as _read_object,
    release_lifecycle_issues as _release_lifecycle_issues,
)
from verify.release_lifecycle_environment import (
    bound_report as _bound_report,
    identity_issues as _identity_issues,
    import_receipt_issues as _import_receipt_issues,
    rollback_issues as _rollback_issues,
    run_document as _run_document,
    run_root as _run_root,
)

ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
PROD_MODES = frozenset({"activated", "dry-run", "prepared"})


def release_lifecycle_issues(release_id: str, *, release_root: Path | None = None) -> list[str]:
    return _release_lifecycle_issues(
        release_id,
        release_root=release_root or RELEASE_ROOT,
    )


def environment_lifecycle_issues(
    release_id: str,
    *,
    environment: str,
    import_run_id: str | None,
    verify_run_id: str | None = None,
    prod_mode: str = "activated",
    rollback_from_release_id: str | None = None,
    release_root: Path | None = None,
    output_root: Path | None = None,
) -> list[str]:
    """Verify one environment independently from real append-only run evidence."""

    issues = release_lifecycle_issues(release_id, release_root=release_root)
    if issues:
        return issues
    if environment not in ENVIRONMENTS:
        return [f"environment must be one of {sorted(ENVIRONMENTS)}"]
    if prod_mode not in PROD_MODES:
        return [f"prodMode must be one of {sorted(PROD_MODES)}"]
    if environment != "prod" and prod_mode != "activated":
        return ["prodMode prepared/dry-run is only valid for prod"]
    if not import_run_id:
        if environment == "prod" and prod_mode == "prepared":
            return []
        return ["importRunId is required for activated/dry-run lifecycle proof"]

    releases = release_root or RELEASE_ROOT
    outputs = output_root or OUTPUT_ROOT
    release = releases / release_id
    header = _read_object(
        payload_file(release, "release.json"),
        label="release header",
        issues=issues,
    )
    desired = _read_object(
        payload_file(release, "desired_state.json"),
        label="desired state",
        issues=issues,
    )
    attestation = _read_object(
        attestation_root(release) / RELEASE_ATTESTATION,
        label="release attestation",
        issues=issues,
    )
    desired_refs = desired.get("desiredRefs") or {}
    normalized_refs = {kind: sorted(str(ref) for ref in desired_refs.get(kind) or []) for kind in ("entities", "posts", "creators", "tags")}

    import_run = _run_root(
        output_root=outputs,
        environment=environment,
        release_id=release_id,
        run_id=import_run_id,
    )
    run = _run_document(
        import_run,
        "run.json",
        "environment_release_run",
        issues=issues,
    )
    result = _run_document(
        import_run,
        "result.json",
        "environment_release_result",
        issues=issues,
    )
    if not run or not result:
        return issues
    for document, filename in ((run, "run.json"), (result, "result.json")):
        issues += _identity_issues(
            document,
            path=import_run / filename,
            environment_field="environment",
            environment=environment,
            release_id=release_id,
        )
        if document.get("runId") != import_run_id:
            issues.append(f"{import_run / filename}: runId does not match directory")
    if run.get("kind") not in {"apply", "rollback"}:
        issues.append(f"{import_run / 'run.json'}: import run kind must be apply or rollback")
    issues.extend(
        _rollback_issues(
            run=run,
            import_run=import_run,
            release_id=release_id,
            rollback_from_release_id=rollback_from_release_id,
        )
    )

    expected_result_status = {
        "activated": "completed",
        "dry-run": "dry_run",
        "prepared": "prepared",
    }[prod_mode]
    if result.get("status") != expected_result_status:
        issues.append(f"{import_run / 'result.json'}: status does not prove prodMode={prod_mode}")
    applied_path = import_run / "applied_ref.json"
    if prod_mode == "activated":
        applied = _run_document(
            import_run,
            "applied_ref.json",
            "applied_release_ref",
            issues=issues,
        )
        if applied:
            issues += _identity_issues(
                applied,
                path=applied_path,
                environment_field="environment",
                environment=environment,
                release_id=release_id,
            )
    elif applied_path.exists():
        issues.append(f"{applied_path}: {prod_mode} run must not claim activation")

    if prod_mode in {"activated", "dry-run"}:
        issues.extend(
            _import_receipt_issues(
                run=import_run,
                result=result,
                output_root=outputs,
                environment=environment,
                release_id=release_id,
                release_kind=str(header["releaseKind"]),
                manifest_digest=str(attestation["payloadSha256"]),
                desired_refs=normalized_refs,
                dry_run=prod_mode == "dry-run",
            )
        )
    else:
        bound_imports = [
            field
            for field in (
                "tagImportReportRef",
                "creatorImportReportRef",
                "contentImportReportRef",
                "homepageImportReportRef",
            )
            if result.get(field)
        ]
        if bound_imports:
            issues.append(f"{import_run / 'result.json'}: prepared run must not bind import receipts")

    if prod_mode != "activated":
        if verify_run_id:
            issues.append(f"prodMode={prod_mode} must not claim consumer activation verification")
        return issues
    if not verify_run_id:
        issues.append("verifyRunId is required after activation")
        return issues

    verify_run = _run_root(
        output_root=outputs,
        environment=environment,
        release_id=release_id,
        run_id=verify_run_id,
    )
    verify_identity = _run_document(
        verify_run,
        "run.json",
        "environment_release_run",
        issues=issues,
    )
    verify_result = _run_document(
        verify_run,
        "result.json",
        "environment_release_result",
        issues=issues,
    )
    if not verify_identity or not verify_result:
        return issues
    if verify_identity.get("kind") != "verify":
        issues.append(f"{verify_run / 'run.json'}: verification run kind must be verify")
    if verify_result.get("status") != "completed":
        issues.append(f"{verify_run / 'result.json'}: verification is not completed")
    if verify_result.get("importRunId") != import_run_id:
        issues.append(f"{verify_run / 'result.json'}: verification does not bind import run")
    for document, filename in (
        (verify_identity, "run.json"),
        (verify_result, "result.json"),
    ):
        issues += _identity_issues(
            document,
            path=verify_run / filename,
            environment_field="environment",
            environment=environment,
            release_id=release_id,
        )
    if header["releaseKind"] == "empty_baseline":
        baseline = _bound_report(
            result=verify_result,
            field="baselineApiVerificationRef",
            run=verify_run,
            filename="baseline-api-verification.json",
            schema_name="baseline_api_verification",
            output_root=outputs,
            issues=issues,
        )
        if baseline:
            issues += _identity_issues(
                baseline,
                path=verify_run / "baseline-api-verification.json",
                environment_field="environment",
                environment=environment,
                release_id=release_id,
            )
    else:
        homepage = _bound_report(
            result=verify_result,
            field="homepageApiVerificationRef",
            run=verify_run,
            filename="homepage-api-verification.json",
            schema_name="homepage_api_verification",
            output_root=outputs,
            issues=issues,
        )
        if homepage:
            issues += _identity_issues(
                homepage,
                path=verify_run / "homepage-api-verification.json",
                environment_field="environment",
                environment=environment,
                release_id=release_id,
            )
        if normalized_refs["posts"]:
            post = _bound_report(
                result=verify_result,
                field="postApiVerificationRef",
                run=verify_run,
                filename="post-api-verification.json",
                schema_name="post_api_verification",
                output_root=outputs,
                issues=issues,
            )
            if post:
                issues += _identity_issues(
                    post,
                    path=verify_run / "post-api-verification.json",
                    environment_field="environment",
                    environment=environment,
                    release_id=release_id,
                )
            readiness = _bound_report(
                result=verify_result,
                field="releaseReadinessRef",
                run=verify_run,
                filename="release-readiness.json",
                schema_name="environment_release_readiness",
                output_root=outputs,
                issues=issues,
            )
            if readiness:
                issues.extend(
                    environment_release_readiness_issues(
                        readiness,
                        homepage_verification=homepage,
                        post_verification=post,
                        release=release,
                        output_root=outputs,
                        import_run=import_run,
                        verify_run=verify_run,
                        attestation=attestation,
                        desired_refs=normalized_refs,
                        environment=environment,
                        release_id=release_id,
                        import_run_id=import_run_id,
                        verify_run_id=verify_run_id,
                    )
                )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证不可变 release 生命周期证据")
    parser.add_argument("--release", required=True)
    parser.add_argument("--environment", choices=sorted(ENVIRONMENTS))
    parser.add_argument("--import-run")
    parser.add_argument("--verify-run")
    parser.add_argument("--rollback-from-release")
    parser.add_argument(
        "--prod-mode",
        choices=sorted(PROD_MODES),
        default="activated",
    )
    args = parser.parse_args(argv)
    if args.environment:
        issues = environment_lifecycle_issues(
            args.release,
            environment=args.environment,
            import_run_id=args.import_run,
            verify_run_id=args.verify_run,
            prod_mode=args.prod_mode,
            rollback_from_release_id=args.rollback_from_release,
        )
    else:
        issues = release_lifecycle_issues(args.release)
    if issues:
        print("[verify_release_lifecycle] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    environment = f" environment={args.environment} prodMode={args.prod_mode}" if args.environment else ""
    print(f"[verify_release_lifecycle] OK release={args.release}{environment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
