"""Receipt-protocol publish chain: qualify, materialize, deliver, promote (DEC-027).

`release publish-execution --execution-id <id> [--apply]` 是 receipt 协议
execution 在 publish 阶段的唯一 CLI。plan 模式只校验与报告；apply 模式执行
物化 → pool delivery intent → 单对象事务（与 DEC-026 同轨），逐对象幂等。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import read_json


class ReceiptPublishError(ValueError):
    """The execution is not eligible for the receipt-protocol publish chain."""


def _receipt_chain_precondition(execution_id: str) -> None:
    """最新语义阶段 receipt 必须是 5.review pass；publish 重入 receipt 合法。"""
    from content.execution.stage_receipt import list_receipt_files, load_receipt

    entries = list_receipt_files(execution_id)
    if not entries:
        raise ReceiptPublishError("execution has no stage receipts")
    semantic_stages = {"0.plan", "sources", "1.download", "2.quality", "3.compose", "4.draft", "5.review"}
    latest_semantic: dict | None = None
    for _sequence, stage, path in reversed(entries):
        if stage in semantic_stages:
            latest_semantic = load_receipt(path)
            break
    if latest_semantic is None:
        raise ReceiptPublishError("receipt chain has no semantic-stage receipt")
    if latest_semantic["stage"] != "5.review" or latest_semantic["verdict"] != "pass":
        raise ReceiptPublishError(
            "latest semantic receipt is not a passing 5.review: "
            f"{latest_semantic['stage']}={latest_semantic['verdict']}"
        )


def _frozen_carrier(execution_id: str) -> str:
    """The one carrier this execution froze, which decides the whole publish shape."""
    from content.execution.spec_contract import ExecutionSpec
    from content.execution.store import load_spec

    spec = ExecutionSpec.from_mapping(load_spec(execution_id))
    carriers = [carrier.value for carrier in spec.content.carriers]
    if len(carriers) != 1:
        raise ReceiptPublishError("execution must freeze exactly one content carrier")
    return carriers[0]


def _post_targets(
    execution_id: str, *, carrier: str
) -> list[tuple[dict[str, Any], str, Path]]:
    """返回 (target, post_ref, object_dir)；post_ref 为 posts/ 下相对路径。"""
    from content.execution.workspace import load_frozen_target_set
    from core.paths import execution_root

    root = execution_root(execution_id)
    rows: list[tuple[dict[str, Any], str, Path]] = []
    for target in load_frozen_target_set(execution_id)["targets"]:
        angle = str(target.get("publishAngle") or "").strip()
        title = str(target.get("publishTitle") or "").strip()
        seq = int(target.get("publishSeq") or 1)
        if not angle or not title:
            raise ReceiptPublishError(
                f"target lacks frozen publish coordinates: {target.get('name')}"
            )
        post_ref = f"{carrier}/{angle}/{title}/{seq}"
        rows.append((target, post_ref, root / "posts" / post_ref))
    return rows


def publish_receipt_execution(
    execution_id: str, *, apply: bool = False
) -> dict[str, Any]:
    from content.execution.workspace import write_publish_ref
    from content.release.canonical.post_promotion import promote_post_object
    from content.release.canonical.receipt_materialize import (
        ReceiptMaterializeError,
        materialize_receipt_post,
    )
    from verify.verify_content_execution_layout import (
        content_execution_layout_issues,
    )

    _receipt_chain_precondition(execution_id)
    layout_issues = content_execution_layout_issues(execution_id=execution_id)
    if layout_issues:
        raise ReceiptPublishError(
            "execution layout is not publishable:\n  - " + "\n  - ".join(layout_issues)
        )
    carrier = _frozen_carrier(execution_id)
    if carrier == "homepage":
        return _publish_homepage_execution(execution_id, apply=apply)
    targets = _post_targets(execution_id, carrier=carrier)
    results: list[dict[str, Any]] = []
    promoted_refs: list[str] = []
    for target, post_ref, object_dir in targets:
        attestation_path = object_dir / "5.review/attestation.json"
        attestation = (
            read_json(attestation_path) if attestation_path.is_file() else None
        )
        row: dict[str, Any] = {"postRef": f"posts/{post_ref}", "status": "planned"}
        if not isinstance(attestation, dict) or attestation.get("decision") != "approved":
            row.update(status="excluded", reason="attestation is not approved")
            results.append(row)
            continue
        if not apply:
            from content.release.canonical.receipt_materialize import (
                _load_frozen_inputs,
            )

            try:
                _load_frozen_inputs(object_dir)
            except ReceiptMaterializeError as exc:
                row.update(status="blocked", reason=str(exc))
            results.append(row)
            continue
        try:
            materialize_receipt_post(
                execution_id, object_dir=object_dir, target=target
            )
            intent = _delivery_intent(
                execution_id,
                carrier=post_ref.split("/", 1)[0],
                post_ref=post_ref,
                object_dir=object_dir,
            )
            promotion = promote_post_object(
                execution_id,
                post_ref,
                pool_delivery_intent=intent,
                qualified_refs=(post_ref,),
            )
        except (ReceiptMaterializeError, ValueError) as exc:
            row.update(status="blocked", reason=str(exc))
            results.append(row)
            continue
        row.update(
            status="promoted",
            transactionId=promotion["transactionId"],
            canonicalObjectRef=promotion["canonicalObjectRef"],
        )
        promoted_refs.append(post_ref)
        results.append(row)
    outcome = {
        "executionId": execution_id,
        "mode": "apply" if apply else "plan",
        "objects": results,
        "promoted": len(promoted_refs),
        "blocked": sum(1 for row in results if row["status"] == "blocked"),
        "excluded": sum(1 for row in results if row["status"] == "excluded"),
    }
    if apply:
        if not promoted_refs:
            raise ReceiptPublishError(
                "receipt publish promoted zero objects: "
                + "; ".join(
                    f"{row['postRef']}: {row.get('reason', row['status'])}"
                    for row in results
                )
            )
        write_publish_ref(execution_id, post_refs=promoted_refs)
    return outcome


def _homepage_targets(execution_id: str) -> list[tuple[str, Path]]:
    """返回 (canonical_ref, object_dir)；canonical_ref 为 domain/type/name。

    homepage 的对象身份是实体路径本身，没有 publishAngle/publishTitle/seq 这组
    发表坐标可冻结，因此目标集来自 execution 工作包里实际存在的实体对象，而不是
    frozen target set 的投影。
    """
    from core.entity_object import collect_execution_entity_objects

    try:
        rows = collect_execution_entity_objects(
            execution_id, enforce_type_consistency=True
        )
    except ValueError as exc:
        raise ReceiptPublishError(f"execution entity objects conflict: {exc}") from exc
    if not rows:
        raise ReceiptPublishError("homepage execution carries no entity object")
    targets: list[tuple[str, Path]] = []
    for row in rows:
        canonical_ref = str(row["entityRel"]).removeprefix("entities/").strip("/")
        if len(canonical_ref.split("/")) < 3:
            raise ReceiptPublishError(
                f"entity object ref must be domain/type/name: {row['entityRel']}"
            )
        targets.append((canonical_ref, Path(row["entityDir"])))
    return targets


def _publish_homepage_execution(
    execution_id: str, *, apply: bool
) -> dict[str, Any]:
    """Publish one homepage execution's entity objects through the receipt chain.

    A homepage object is an entity page, not a post: it has no publish coordinates
    and its canonical home is `entities/`, so it needs its own target discovery and
    its own transaction. What it must not have is its own admission judgment — the
    5.review attestation that qualifies a post is the same one that qualifies an
    entity, and the entity transaction reads that same document.
    """
    from content.execution.closure.pool_delivery import write_pool_delivery_intent
    from content.release.canonical.publish_homepage_object import publish_homepage_object
    from content.execution.workspace import write_publish_ref

    results: list[dict[str, Any]] = []
    promoted_refs: list[str] = []
    for canonical_ref, object_dir in _homepage_targets(execution_id):
        entity_ref = f"/entity/{canonical_ref}"
        row: dict[str, Any] = {"entityRef": entity_ref, "status": "planned"}
        attestation_path = object_dir / "5.review/attestation.json"
        attestation = (
            read_json(attestation_path) if attestation_path.is_file() else None
        )
        if (
            not isinstance(attestation, dict)
            or attestation.get("decision") != "approved"
        ):
            row.update(status="excluded", reason="attestation is not approved")
            results.append(row)
            continue
        if not apply:
            for required in ("_entity.json", "manifest.json", "page.md"):
                if not (object_dir / required).is_file():
                    row.update(
                        status="blocked",
                        reason=f"entity object lacks frozen input: {required}",
                    )
                    break
            results.append(row)
            continue
        try:
            intent, _path = write_pool_delivery_intent(
                execution_id,
                carrier="homepage",
                object_ref=entity_ref,
                content_object_dir=f"entities/{canonical_ref}",
            )
            promotion = publish_homepage_object(
                execution_id,
                entity_ref,
                pool_delivery_intent=intent,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            row.update(status="blocked", reason=str(exc))
            results.append(row)
            continue
        row.update(
            status="promoted",
            transactionId=promotion["transactionId"],
            canonicalObjectRef=promotion["canonicalObjectRef"],
        )
        promoted_refs.append(entity_ref)
        results.append(row)
    outcome = {
        "executionId": execution_id,
        "mode": "apply" if apply else "plan",
        "carrier": "homepage",
        "objects": results,
        "promoted": len(promoted_refs),
        "blocked": sum(1 for row in results if row["status"] == "blocked"),
        "excluded": sum(1 for row in results if row["status"] == "excluded"),
    }
    if apply:
        if not promoted_refs:
            raise ReceiptPublishError(
                "receipt publish promoted zero objects: "
                + "; ".join(
                    f"{row['entityRef']}: {row.get('reason', row['status'])}"
                    for row in results
                )
            )
        write_publish_ref(execution_id, entity_refs=promoted_refs)
    return outcome


def _delivery_intent(
    execution_id: str, *, carrier: str, post_ref: str, object_dir: Path
) -> dict[str, Any]:
    from content.execution.closure.pool_delivery import write_pool_delivery_intent

    manifest = read_json(object_dir / "manifest.json")
    intent, _path = write_pool_delivery_intent(
        execution_id,
        carrier=carrier,
        object_ref=str(manifest["topicId"]),
        content_object_dir=f"posts/{post_ref}",
    )
    return intent


def handle_publish_execution(args: object) -> None:
    import json

    try:
        report = publish_receipt_execution(
            str(getattr(args, "execution_id")),
            apply=bool(getattr(args, "apply", False)),
        )
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[release publish-execution] GATE_BLOCK {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


__all__ = [
    "ReceiptPublishError",
    "handle_publish_execution",
    "publish_receipt_execution",
]
