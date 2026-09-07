"""Validate release import receipts and rollback evidence."""

from __future__ import annotations

from pathlib import Path

from verify.release_lifecycle_attestation import read_object, validate_document


def run_root(
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    run_id: str,
) -> Path:
    return (
        output_root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / run_id
    )


def run_document(
    run: Path,
    name: str,
    schema_name: str,
    *,
    issues: list[str],
) -> dict:
    path = run / name
    if not path.is_file():
        issues.append(f"{path}: missing environment lifecycle evidence")
        return {}
    document = read_object(path, label=schema_name, issues=issues)
    if not document:
        return {}
    if not validate_document(
        document,
        path=path,
        schema_name=schema_name,
        issues=issues,
    ):
        return {}
    return document


def bound_report(
    *,
    result: dict,
    field: str,
    run: Path,
    filename: str,
    schema_name: str,
    output_root: Path,
    issues: list[str],
) -> dict:
    expected_path = run / filename
    try:
        expected_ref = expected_path.relative_to(output_root).as_posix()
    except ValueError:
        issues.append(f"{expected_path}: environment run must be below output root")
        return {}
    if result.get(field) != expected_ref:
        issues.append(f"{run / 'result.json'}: {field} does not bind {filename}")
        return {}
    return run_document(run, filename, schema_name, issues=issues)


def identity_issues(
    document: dict,
    *,
    path: Path,
    environment_field: str,
    environment: str,
    release_id: str,
) -> list[str]:
    issues: list[str] = []
    if document.get(environment_field) != environment:
        issues.append(f"{path}: environment does not match run")
    if document.get("releaseId") != release_id:
        issues.append(f"{path}: releaseId does not match run")
    return issues


def import_receipt_issues(
    *,
    run: Path,
    result: dict,
    output_root: Path,
    environment: str,
    release_id: str,
    release_kind: str,
    manifest_digest: str,
    desired_refs: dict,
    dry_run: bool,
) -> list[str]:
    issues: list[str] = []
    # The projection receipts and the content import receipt spell the applied
    # state with different literals in their own schemas, so each is compared
    # against the value its producer is allowed to write.
    expected_status = "dry-run" if dry_run else "active"
    expected_content_status = "dry-run" if dry_run else "imported"
    receipts = {
        name: bound_report(
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
            (
                "creator",
                "creatorImportReportRef",
                "creator-import.json",
                "creator_import_report",
            ),
            ("content", "contentImportReportRef", "import.json", "import_report"),
            (
                "homepage",
                "homepageImportReportRef",
                "homepage-import.json",
                "homepage_import_report",
            ),
        )
    }
    tag, creator, content, homepage = (
        receipts[name] for name in ("tag", "creator", "content", "homepage")
    )
    for document, filename, environment_field in (
        (tag, "tag-import.json", "environment"),
        (creator, "creator-import.json", "environment"),
        (content, "import.json", "environment"),
        (homepage, "homepage-import.json", "env"),
    ):
        if document:
            issues += identity_issues(
                document,
                path=run / filename,
                environment_field=environment_field,
                environment=environment,
                release_id=release_id,
            )
    if tag:
        if tag.get("status") != expected_status:
            issues.append(
                f"{run / 'tag-import.json'}: status does not match run mode"
            )
        if tag.get("releaseKind") != release_kind:
            issues.append(f"{run / 'tag-import.json'}: releaseKind drift")
        if tag.get("tagRefs") != desired_refs["tags"]:
            issues.append(
                f"{run / 'tag-import.json'}: tag readback differs from desired state"
            )
    if creator:
        if creator.get("status") != expected_status:
            issues.append(
                f"{run / 'creator-import.json'}: status does not match run mode"
            )
        if creator.get("verifiedCreatorIds") != desired_refs["creators"]:
            issues.append(
                f"{run / 'creator-import.json'}: creator readback differs from desired state"
            )
    if content:
        if content.get("status") != expected_content_status:
            issues.append(f"{run / 'import.json'}: status does not match run mode")
        if content.get("manifestDigest") != manifest_digest:
            issues.append(
                f"{run / 'import.json'}: manifestDigest drift from immutable payload"
            )
        counts = content.get("counts") or {}
        if counts.get("entitiesLoaded") != len(desired_refs["entities"]):
            issues.append(
                f"{run / 'import.json'}: entity readback count differs from desired state"
            )
        if counts.get("postsLoaded") != len(desired_refs["posts"]):
            issues.append(
                f"{run / 'import.json'}: post readback count differs from desired state"
            )
        post_refs = sorted(
            str(row.get("postRef") or "")
            for row in content.get("postBindings") or []
            if isinstance(row, dict)
        )
        if post_refs != desired_refs["posts"]:
            issues.append(
                f"{run / 'import.json'}: post readback differs from desired state"
            )
    if homepage:
        if homepage.get("dryRun") is not dry_run:
            issues.append(
                f"{run / 'homepage-import.json'}: dryRun does not match run mode"
            )
        entity_refs = sorted((homepage.get("entityRefToHomepageId") or {}).keys())
        if entity_refs != desired_refs["entities"]:
            issues.append(
                f"{run / 'homepage-import.json'}: homepage readback differs from desired state"
            )
        if homepage.get("issues") != []:
            issues.append(
                f"{run / 'homepage-import.json'}: importer issues must be empty"
            )
    return issues


def rollback_issues(
    *,
    run: dict,
    import_run: Path,
    release_id: str,
    rollback_from_release_id: str | None,
) -> list[str]:
    issues: list[str] = []
    if run.get("kind") == "rollback":
        rollback = run_document(
            import_run,
            "rollback_ref.json",
            "rollback_release_ref",
            issues=issues,
        )
        if rollback:
            if rollback.get("rollbackTo") != release_id:
                issues.append(
                    f"{import_run / 'rollback_ref.json'}: rollbackTo drift"
                )
            source = str(rollback.get("rollbackFromReleaseId") or "")
            if source == release_id:
                issues.append(
                    f"{import_run / 'rollback_ref.json'}: rollbackFromReleaseId must differ"
                )
            if rollback_from_release_id and source != rollback_from_release_id:
                issues.append(
                    f"{import_run / 'rollback_ref.json'}: rollbackFromReleaseId drift"
                )
    elif rollback_from_release_id:
        issues.append("rollbackFromReleaseId requires a rollback import run")
    return issues
