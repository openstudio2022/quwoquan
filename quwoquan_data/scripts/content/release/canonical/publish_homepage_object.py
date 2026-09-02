"""Canonical homepage entity publish transaction."""
from __future__ import annotations

from collections.abc import Mapping

from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)

@canonical_publish_serialized
def publish_homepage_object(
    execution_id: str,
    object_ref: str,
    *,
    pool_delivery_intent: Mapping[str, object] | None = None,
) -> dict[str, str]:
    """Apply one reviewed homepage through the canonical object transaction."""
    import hashlib

    from core.io import read_json
    from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
    from core.tree_integrity import tree_integrity_stats

    from content.execution.workspace import execution_root
    from content.release.canonical.application import apply_object_transaction
    from content.release.canonical.canonical_inventory import (
        load_or_bootstrap_inventory,
    )
    from content.release.canonical.object_transaction import (
        build_entity_object_transaction_package,
    )
    from content.release.canonical.object_transaction_audit import (
        audit_object_transaction,
    )

    canonical_ref = str(object_ref or "").removeprefix("/entity/").strip("/")
    if len(canonical_ref.split("/")) < 3:
        raise ValueError(f"homepage objectRef 无效：{object_ref!r}")
    transaction_id = (
        f"{execution_id}--entity-"
        f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    execution_dir = execution_root(execution_id)
    if pool_delivery_intent is None:
        from content.execution.closure.pool_delivery import (
            pool_delivery_intent_path,
        )

        intent_path = pool_delivery_intent_path(
            execution_id,
            carrier="homepage",
            object_ref=object_ref,
        )
        loaded_intent = read_json(intent_path)
        if not isinstance(loaded_intent, dict):
            raise ValueError("pool delivery homepage intent must be an object")
        pool_delivery_intent = loaded_intent
    package_root = execution_dir / "evidence/object-transactions" / transaction_id
    apply_report = (
        OUTPUT_ROOT
        / "data/local/workspace/object-transactions"
        / transaction_id
        / "apply_report.json"
    )
    canonical_object = PUBLISH_ROOT / "entities" / canonical_ref
    build_entity_object_transaction_package(
        execution_root=execution_dir,
        object_ref=f"/entity/{canonical_ref}",
        transaction_id=transaction_id,
        package_root=package_root,
        pool_delivery_intent=pool_delivery_intent,
    )
    admission_result = "replayed"
    if apply_report.is_file() and (canonical_object / "manifest.json").is_file():
        if (
            tree_integrity_stats(canonical_object)["merkleRoot"]
            != tree_integrity_stats(package_root / "object")["merkleRoot"]
        ):
            raise RuntimeError(
                f"completed transaction canonical object drift: /entity/{canonical_ref}"
            )
        applied = read_json(apply_report)
    else:
        admission_result = "appended"
        before = load_or_bootstrap_inventory(PUBLISH_ROOT)["stats"]["merkleRoot"]
        audit = audit_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            expected_canonical_merkle=before,
        )
        applied = apply_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
        )
    return {
        "transactionId": transaction_id,
        "applyReportRef": apply_report.relative_to(OUTPUT_ROOT).as_posix(),
        "canonicalObjectRef": f"entities/{canonical_ref}",
        "canonicalObjectSha256": str(
            tree_integrity_stats(canonical_object)["merkleRoot"]
        ),
        "objectClosureDigest": str(applied.get("objectClosureDigest") or ""),
        "admissionResult": admission_result,
    }
