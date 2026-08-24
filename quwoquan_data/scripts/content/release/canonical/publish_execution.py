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


def _post_targets(execution_id: str) -> list[tuple[dict[str, Any], str, Path]]:
    """返回 (target, post_ref, object_dir)；post_ref 为 posts/ 下相对路径。"""
    from content.execution.spec_contract import ExecutionSpec
    from content.execution.store import load_spec
    from content.execution.workspace import load_frozen_target_set
    from core.paths import execution_root

    spec = ExecutionSpec.from_mapping(load_spec(execution_id))
    carriers = [carrier.value for carrier in spec.content.carriers]
    if carriers == ["homepage"]:
        raise ReceiptPublishError(
            "homepage carrier publish is not wired into the receipt protocol yet"
        )
    if len(carriers) != 1:
        raise ReceiptPublishError("execution must freeze exactly one content carrier")
    carrier = carriers[0]
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
    targets = _post_targets(execution_id)
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
