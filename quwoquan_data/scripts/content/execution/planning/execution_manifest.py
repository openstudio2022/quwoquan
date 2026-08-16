"""Immutable execution-manifest construction."""

from __future__ import annotations

from content.execution.workspace import (
    MANIFEST_FILENAME,
    REQUEST_REF,
    TARGET_SET_REF,
    Any,
    Mapping,
    SelectionPolicy,
    _file_sha256,
    core_paths,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
    ensure_execution_work_package_layout,
    execution_request_path,
    execution_root,
    frozen_target_set_digest,
    load_execution_manifest,
    parse_execution_id,
    read_json,
    validate_execution_id,
    write_json,
    yaml,
)


def create_execution_manifest(
    *,
    execution_id: str,
    recipe_ref: str,
    request: dict[str, Any],
    selection_policy: SelectionPolicy,
    target_set_ref: str,
    target_set_digest: str,
    retry_of: str | None = None,
    semantic_selection_id: str = "default",
    semantic_preflight_binding: Mapping[str, Any] | None = None,
    semantic_preflight_require_fresh: bool = True,
) -> dict[str, Any]:
    """Create exactly one immutable execution manifest and work-package tree.

    Reusing an existing ID is a resume only when its immutable inputs match.
    A new attempt must receive a new sequence and point at ``retryOf``.
    """
    identity = parse_execution_id(execution_id)
    root = execution_root(identity.execution_id)
    manifest_path = root / MANIFEST_FILENAME
    recipe_file = core_paths.recipe_path(recipe_ref)
    if not isinstance(selection_policy, SelectionPolicy):
        raise TypeError("selection_policy must be SelectionPolicy")
    if target_set_ref != TARGET_SET_REF:
        raise ValueError(f"targetSetRef must be {TARGET_SET_REF}")
    actual_target_set_digest = frozen_target_set_digest(identity.execution_id)
    if target_set_digest != actual_target_set_digest:
        raise ValueError("targetSetDigest does not match the frozen target set")
    normalized_retry_of = validate_execution_id(retry_of) if retry_of else None
    if normalized_retry_of:
        retry_identity = parse_execution_id(normalized_retry_of)
        comparable = (
            "vertical",
            "content_type",
            "intent",
            "scope",
            "phase",
        )
        if normalized_retry_of == identity.execution_id or any(
            getattr(retry_identity, field) != getattr(identity, field)
            for field in comparable
        ):
            raise ValueError(
                "retryOf must reference an earlier sequence of the same execution scope"
            )
        if retry_identity.sequence >= identity.sequence:
            raise ValueError(
                "retryOf sequence must be lower than the new execution sequence"
            )

    existing_manifest = (
        load_execution_manifest(identity.execution_id)
        if manifest_path.is_file()
        else None
    )
    from content.execution.planning.semantic_preflight_admission import (
        resolve_manifest_preflight_binding,
    )

    normalized_preflight_binding = resolve_manifest_preflight_binding(
        existing_manifest=existing_manifest,
        requested_binding=semantic_preflight_binding,
        semantic_selection_id=semantic_selection_id,
        output_root=core_paths.OUTPUT_ROOT,
        require_requested_fresh=(
            semantic_preflight_require_fresh and existing_manifest is None
        ),
    )
    if existing_manifest is not None:
        # A v2 work package is its own immutable execution authority.  Resume
        # must not rebuild either identity from the changing checkout: source
        # definitions and the executor bundle were frozen at first creation.
        # The exact request/target/preflight/family lineage is still checked
        # below, so this does not turn resume into a compatibility path.
        family_ref = existing_manifest.get("familyRef")
        if not isinstance(family_ref, Mapping) or family_ref.get("ref") != recipe_ref:
            raise ValueError("execution manifest familyRef drift")
        if existing_manifest.get("semanticSelectionId") != semantic_selection_id:
            raise ValueError("execution manifest semanticSelectionId drift")
        if existing_manifest.get("retryOf") != normalized_retry_of:
            raise ValueError("execution manifest retryOf drift")
        if existing_manifest.get("targetSetRef") != target_set_ref:
            raise ValueError("execution manifest targetSetRef drift")
        if existing_manifest.get("targetSetDigest") != target_set_digest:
            raise ValueError("execution manifest targetSetDigest drift")
        if (
            existing_manifest.get("semanticPreflightReceipt")
            != normalized_preflight_binding
        ):
            raise ValueError("execution manifest semantic preflight binding drift")
        request_path = execution_request_path(identity.execution_id)
        if not request_path.is_file() or read_json(request_path) != request:
            raise ValueError("execution request is immutable; create a new sequence")
        return existing_manifest

    if not recipe_file.is_file():
        raise FileNotFoundError(f"recipeRef does not exist: {recipe_ref}")
    recipe_payload = yaml.safe_load(recipe_file.read_text(encoding="utf-8"))
    if not isinstance(recipe_payload, dict):
        raise TypeError(f"recipe must be an object: {recipe_file}")
    from content.execution.planning.semantic_selection import semantic_manifest_identity

    semantic_identity = semantic_manifest_identity(
        recipe_payload,
        semantic_selection_id=semantic_selection_id,
        retry_of=normalized_retry_of,
    )
    source_identity = current_source_definition_snapshot().to_document()
    execution_bundle_identity = current_execution_bundle_identity().to_document()
    candidate = {
        "executionId": identity.execution_id,
        "familyRef": {"ref": recipe_ref, "sha256": _file_sha256(recipe_file)},
        "sourceDigest": source_identity,
        "executionBundle": execution_bundle_identity,
        **semantic_identity,
        "requestRef": REQUEST_REF,
        "targetSetRef": target_set_ref,
        "targetSetDigest": target_set_digest,
        "retryOf": normalized_retry_of,
    }
    if normalized_preflight_binding is not None:
        candidate["semanticPreflightReceipt"] = normalized_preflight_binding
    ensure_execution_work_package_layout(identity.execution_id)
    request_path = execution_request_path(identity.execution_id)
    if request_path.is_file():
        existing_request = read_json(request_path)
        if existing_request != request:
            raise ValueError("execution request is immutable; create a new sequence")
    else:
        write_json(request_path, request)
    from core.schema import assert_valid

    assert_valid(
        candidate,
        "execution",
        "content_execution_manifest",
        label=f"execution_manifest:{identity.execution_id}",
    )
    write_json(manifest_path, candidate)
    return candidate
