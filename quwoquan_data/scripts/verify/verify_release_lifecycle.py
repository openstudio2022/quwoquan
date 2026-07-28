#!/usr/bin/env python3
"""Verify one immutable data release has the minimum lifecycle evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.release_attestation import (
    ReleaseAttestation,
    ReleaseAttestationError,
)
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from core.source_digest import SourceDigest, SourceDigestError

RELEASE_ATTESTATION = "release.json"
ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
PROD_MODES = frozenset({"activated", "dry-run", "prepared"})


def _read_object(path: Path, *, label: str, issues: list[str]) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"{path}: invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"{path}: {label} must be an object")
        return {}
    return payload


def _validate_document(
    document: dict,
    *,
    path: Path,
    schema_name: str,
    issues: list[str],
) -> bool:
    try:
        assert_valid(
            document,
            "release",
            schema_name,
            label=f"{schema_name}:{path}",
        )
    except (FileNotFoundError, ValueError) as exc:
        issues.append(str(exc))
        return False
    return True


def _source_digests(
    document: dict,
    *,
    path: Path,
    issues: list[str],
) -> tuple[SourceDigest, ...] | None:
    raw_value = document.get("sourceDigests")
    if not isinstance(raw_value, list):
        issues.append(f"{path}: sourceDigests must be an array")
        return None
    try:
        source_digests = tuple(SourceDigest.from_document(item) for item in raw_value)
    except SourceDigestError as exc:
        issues.append(f"{path}: {exc}")
        return None
    values = tuple(item.digest for item in source_digests)
    if not values or values != tuple(sorted(set(values))):
        issues.append(f"{path}: sourceDigests must be sorted and contain no duplicates")
        return None
    return source_digests


def release_lifecycle_issues(release_id: str, *, release_root: Path | None = None) -> list[str]:
    root = (release_root or RELEASE_ROOT) / release_id
    required = (
        payload_file(root, "release.json"),
        payload_file(root, "desired_state.json"),
        attestation_root(root) / RELEASE_ATTESTATION,
    )
    issues = [f"{path}: missing immutable release evidence" for path in required if not path.is_file()]
    release_file = payload_file(root, "release.json")
    desired_file = payload_file(root, "desired_state.json")
    aggregate_file = attestation_root(root) / RELEASE_ATTESTATION
    if not release_file.is_file() or not desired_file.is_file() or not aggregate_file.is_file():
        return issues

    header = _read_object(release_file, label="release header", issues=issues)
    desired = _read_object(desired_file, label="desired state", issues=issues)
    aggregate = _read_object(aggregate_file, label="aggregate attestation", issues=issues)
    if not header or not desired or not aggregate:
        return issues
    if not _validate_document(
        header,
        path=release_file,
        schema_name="release_header",
        issues=issues,
    ):
        return issues
    if not _validate_document(
        desired,
        path=desired_file,
        schema_name="release_desired_state",
        issues=issues,
    ):
        return issues
    try:
        assert_valid(
            aggregate,
            "release",
            "release_attestation",
            label=f"release_attestation:{release_id}",
        )
    except (FileNotFoundError, ValueError) as exc:
        issues.append(str(exc))
        return issues
    try:
        typed_attestation = ReleaseAttestation.from_document(aggregate)
    except ReleaseAttestationError as exc:
        issues.append(f"{aggregate_file}: {exc}")
        return issues

    if header.get("releaseId") != release_id:
        issues.append(f"{release_file}: releaseId does not match directory")
    release_kind = header.get("releaseKind")
    if release_kind not in {"content", "empty_baseline"}:
        issues.append(f"{release_file}: releaseKind is invalid")
    header_execution_ids = header.get("executionIds")
    if not isinstance(header_execution_ids, list):
        issues.append(f"{release_file}: executionIds must be an array")
        header_execution_ids = []
    desired_refs = desired.get("desiredRefs")
    if not isinstance(desired_refs, dict):
        issues.append(f"{desired_file}: desiredRefs must be an object")
        desired_refs = {}
    entity_refs = desired_refs.get("entities")
    post_refs = desired_refs.get("posts")
    creator_refs = desired_refs.get("creators")
    tag_refs = desired_refs.get("tags")
    if not all(isinstance(refs, list) for refs in (entity_refs, post_refs, creator_refs, tag_refs)):
        issues.append(f"{desired_file}: all desiredRefs kinds must be arrays")
        return issues
    if typed_attestation.release_id != release_id:
        issues.append(f"{aggregate_file}: releaseId does not match directory")
    if typed_attestation.release_kind.value != release_kind:
        issues.append(f"{aggregate_file}: releaseKind drift from release header")
    if sorted(typed_attestation.execution_ids) != sorted(header_execution_ids):
        issues.append(f"{aggregate_file}: executionIds drift from release header")
    if typed_attestation.canonical_merkle != header.get("canonicalMerkle"):
        issues.append(f"{aggregate_file}: canonicalMerkle drift from release header")
    header_source_digests = _source_digests(
        header,
        path=release_file,
        issues=issues,
    )
    aggregate_source_digests = _source_digests(
        aggregate,
        path=aggregate_file,
        issues=issues,
    )
    if header_source_digests is not None and aggregate_source_digests is not None and header_source_digests != aggregate_source_digests:
        issues.append(f"{aggregate_file}: sourceDigests drift from release header")
    if typed_attestation.entity_count != len(entity_refs):
        issues.append(f"{aggregate_file}: entityCount drift from desired state")
    if typed_attestation.post_count != len(post_refs):
        issues.append(f"{aggregate_file}: postCount drift from desired state")
    if typed_attestation.creator_count != len(creator_refs):
        issues.append(f"{aggregate_file}: creatorCount drift from desired state")
    if typed_attestation.tag_count != len(tag_refs):
        issues.append(f"{aggregate_file}: tagCount drift from desired state")
    if release_kind == "content" and (not header_execution_ids or not entity_refs):
        issues.append(f"{release_file}: content release requires executionIds and entity refs")
    if release_kind == "empty_baseline" and (header_execution_ids or entity_refs or post_refs or creator_refs or tag_refs):
        issues.append(f"{release_file}: empty baseline must have no executions or desired refs")
    try:
        actual_payload_digest = payload_digest(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        issues.append(f"{root}: cannot compute payload digest: {exc}")
    else:
        if aggregate.get("payloadSha256") != actual_payload_digest:
            issues.append(f"{aggregate_file}: payloadSha256 drift from immutable payload")
    return issues


def _run_root(*, output_root: Path, environment: str, release_id: str, run_id: str) -> Path:
    return output_root / "env" / environment / "runs" / "data-release" / release_id / run_id


def _run_document(run: Path, name: str, schema_name: str, *, issues: list[str]) -> dict:
    path = run / name
    if not path.is_file():
        issues.append(f"{path}: missing environment lifecycle evidence")
        return {}
    document = _read_object(path, label=schema_name, issues=issues)
    if not document:
        return {}
    if not _validate_document(document, path=path, schema_name=schema_name, issues=issues):
        return {}
    return document


def _bound_report(*, result: dict, field: str, run: Path, filename: str, schema_name: str, output_root: Path, issues: list[str]) -> dict:
    expected_path = run / filename
    try:
        expected_ref = expected_path.relative_to(output_root).as_posix()
    except ValueError:
        issues.append(f"{expected_path}: environment run must be below output root")
        return {}
    if result.get(field) != expected_ref:
        issues.append(f"{run / 'result.json'}: {field} does not bind {filename}")
        return {}
    return _run_document(run, filename, schema_name, issues=issues)


def _identity_issues(document: dict, *, path: Path, environment_field: str, environment: str, release_id: str) -> list[str]:
    issues: list[str] = []
    if document.get(environment_field) != environment:
        issues.append(f"{path}: environment does not match run")
    if document.get("releaseId") != release_id:
        issues.append(f"{path}: releaseId does not match run")
    return issues


def _import_receipt_issues(
    *,
    run: Path,
    result: dict,
    output_root: Path,
    environment: str,
    release_id: str,
    release_kind: str,
    desired_refs: dict,
    dry_run: bool,
) -> list[str]:
    issues: list[str] = []
    expected_status = "dry-run" if dry_run else "active"
    receipts = {
        name: _bound_report(
            result=result,
            field=field,
            run=run,
            filename=filename,
            schema_name=schema_name,
            output_root=output_root,
            issues=issues,
        )
        for name, field, filename, schema_name in (
            ("tag", "tagImportReportRef", "tag-import.json", "tag_import_report"),
            ("creator", "creatorImportReportRef", "creator-import.json", "creator_import_report"),
            ("content", "contentImportReportRef", "import.json", "import_report"),
            ("homepage", "homepageImportReportRef", "homepage-import.json", "homepage_import_report"),
        )
    }
    tag, creator, content, homepage = (receipts[name] for name in ("tag", "creator", "content", "homepage"))
    for document, filename, environment_field in (
        (tag, "tag-import.json", "environment"),
        (creator, "creator-import.json", "environment"),
        (content, "import.json", "environment"),
        (homepage, "homepage-import.json", "env"),
    ):
        if document:
            issues += _identity_issues(
                document,
                path=run / filename,
                environment_field=environment_field,
                environment=environment,
                release_id=release_id,
            )
    if tag:
        if tag.get("status") != expected_status:
            issues.append(f"{run / 'tag-import.json'}: status does not match run mode")
        if tag.get("releaseKind") != release_kind:
            issues.append(f"{run / 'tag-import.json'}: releaseKind drift")
        if tag.get("tagRefs") != desired_refs["tags"]:
            issues.append(f"{run / 'tag-import.json'}: tag readback differs from desired state")
    if creator:
        if creator.get("status") != expected_status:
            issues.append(f"{run / 'creator-import.json'}: status does not match run mode")
        if creator.get("verifiedCreatorIds") != desired_refs["creators"]:
            issues.append(f"{run / 'creator-import.json'}: creator readback differs from desired state")
    if content:
        if content.get("status") != expected_status:
            issues.append(f"{run / 'import.json'}: status does not match run mode")
        counts = content.get("counts") or {}
        if counts.get("entitiesLoaded") != len(desired_refs["entities"]):
            issues.append(f"{run / 'import.json'}: entity readback count differs from desired state")
        if counts.get("postsLoaded") != len(desired_refs["posts"]):
            issues.append(f"{run / 'import.json'}: post readback count differs from desired state")
        post_refs = sorted(str(row.get("postRef") or "") for row in content.get("postBindings") or [] if isinstance(row, dict))
        if post_refs != desired_refs["posts"]:
            issues.append(f"{run / 'import.json'}: post readback differs from desired state")
    if homepage:
        if homepage.get("dryRun") is not dry_run:
            issues.append(f"{run / 'homepage-import.json'}: dryRun does not match run mode")
        entity_refs = sorted((homepage.get("entityRefToHomepageId") or {}).keys())
        if entity_refs != desired_refs["entities"]:
            issues.append(f"{run / 'homepage-import.json'}: homepage readback differs from desired state")
        if homepage.get("issues") != []:
            issues.append(f"{run / 'homepage-import.json'}: importer issues must be empty")
    return issues


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
    if run.get("kind") == "rollback":
        rollback = _run_document(
            import_run,
            "rollback_ref.json",
            "rollback_release_ref",
            issues=issues,
        )
        if rollback:
            if rollback.get("rollbackTo") != release_id:
                issues.append(f"{import_run / 'rollback_ref.json'}: rollbackTo drift")
            source = str(rollback.get("rollbackFromReleaseId") or "")
            if source == release_id:
                issues.append(f"{import_run / 'rollback_ref.json'}: rollbackFromReleaseId must differ")
            if rollback_from_release_id and source != rollback_from_release_id:
                issues.append(f"{import_run / 'rollback_ref.json'}: rollbackFromReleaseId drift")
    elif rollback_from_release_id:
        issues.append("rollbackFromReleaseId requires a rollback import run")

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
