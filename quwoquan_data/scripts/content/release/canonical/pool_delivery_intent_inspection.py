"""Read-only physical inspection of reviewed pool-delivery intents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from content.execution.identity import validate_execution_id
from content.release.canonical.object_source_identity import (
    freeze_execution_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from core.schema import assert_valid
from core.tree_integrity import tree_integrity_stats


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_file(root: Path, raw_ref: object) -> Path:
    relative = Path(str(raw_ref or "").strip())
    candidate = root / relative
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or any(
            (root / Path(*relative.parts[:index])).is_symlink()
            for index in range(1, len(relative.parts) + 1)
        )
        or not candidate.is_file()
    ):
        raise ValueError("pool delivery intent reference is unsafe or missing")
    return candidate


def _safe_dir(root: Path, raw_ref: object) -> Path:
    relative = Path(str(raw_ref or "").strip())
    candidate = root / relative
    if (
        relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or any(
            (root / Path(*relative.parts[:index])).is_symlink()
            for index in range(1, len(relative.parts) + 1)
        )
        or not candidate.is_dir()
    ):
        raise ValueError("pool delivery object directory is unsafe or missing")
    return candidate


def _published_identities(
    publish_root: Path,
) -> dict[tuple[str, str, int], set[str]]:
    result: dict[tuple[str, str, int], set[str]] = {}
    for kind, carrier_default in (("entities", "homepage"), ("posts", "")):
        root = publish_root / kind
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("manifest.json")):
            manifest = _read_json(path)
            carrier = carrier_default or str(manifest.get("contentType") or "")
            object_id = (
                str(manifest.get("entityRef") or "")
                if carrier == "homepage"
                else str(manifest.get("contentId") or "")
            )
            version = manifest.get("version", 1)
            execution_id = str(manifest.get("executionId") or "")
            if (
                carrier in {"homepage", "article", "image", "video"}
                and object_id
                and isinstance(version, int)
                and not isinstance(version, bool)
                and execution_id
            ):
                result.setdefault((carrier, object_id, version), set()).add(
                    execution_id
                )
    return result


def inspect_pool_delivery_intents(
    *,
    output_root: Path,
    publish_root: Path,
    execution_ids: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    tasks_root = output_root / "data/tasks"
    published = _published_identities(publish_root)
    pending: dict[tuple[str, str, int], dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    if not execution_ids or not tasks_root.is_dir():
        return [], []
    normalized_ids = tuple(
        sorted({validate_execution_id(value) for value in execution_ids})
    )
    for execution_id in normalized_ids:
        execution_workspace = tasks_root / execution_id
        try:
            manifest = _read_json(execution_workspace / "execution_manifest.json")
            source_identity = freeze_execution_source_identity(
                execution_root=execution_workspace,
                execution_manifest=manifest,
            )
        except (
            KeyError,
            OSError,
            ObjectTransactionError,
            TypeError,
            ValueError,
        ) as exc:
            issues.append(
                {
                    "gate": "delivery",
                    "code": "DATA.POOL.DELIVERY_INTENT_INVALID",
                    "ref": f"data/tasks/{execution_id}/execution_manifest.json:{exc}",
                }
            )
            continue
        intent_root = execution_workspace / "_shared/pool_delivery_intents"
        for path in sorted(intent_root.glob("*.json")):
            ref = path.relative_to(output_root).as_posix()
            try:
                if path.is_symlink():
                    raise ValueError("pool delivery intent path is unsafe")
                intent = _read_json(path)
                assert_valid(
                    intent,
                    "execution",
                    "pool_delivery_intent",
                    label=f"pool delivery intent:{ref}",
                )
                stable = {
                    key: value for key, value in intent.items() if key != "intentId"
                }
                if intent.get("intentId") != _digest(stable):
                    raise ValueError("pool delivery intent digest drift")
                if intent.get("executionId") != execution_id:
                    raise ValueError("pool delivery intent executionId drift")
                review_path = _safe_file(
                    execution_workspace, intent.get("reviewEvidenceRef")
                )
                review = _read_json(review_path)
                if (
                    _file_digest(review_path) != intent.get("reviewEvidenceSha256")
                    or review.get("decision") != "approved"
                ):
                    raise ValueError("pool delivery review evidence drift")
                object_dir = _safe_dir(
                    execution_workspace, intent.get("contentObjectDir")
                )
                if (
                    tree_integrity_stats(object_dir)["merkleRoot"]
                    != intent.get("transactionInputDigest")
                ):
                    raise ValueError("pool delivery transaction input drift")
                carrier = str(intent["carrier"])
                object_id = str(intent.get("contentId") or intent["objectId"])
                version = int(intent["version"])
                key = (carrier, object_id, version)
                delivered_by = published.get(key, set())
                if execution_id in delivered_by:
                    continue
                row = {
                    "carrier": carrier,
                    "contentId": object_id,
                    "version": version,
                    "executionId": execution_id,
                    "sourceIdentityDigest": source_identity["identityDigest"],
                    "intentId": str(intent["intentId"]),
                    "intentRef": ref,
                    "objectRef": str(intent["objectRef"]),
                    "contentObjectDir": object_dir.relative_to(
                        execution_workspace
                    ).as_posix(),
                    "drainCommand": (
                        "python3 -B quwoquan_data/scripts/cli.py task "
                        f"drain-pool-delivery --execution-id {execution_id}"
                    ),
                }
                old = pending.get(key)
                if old is not None and old["intentId"] != row["intentId"]:
                    raise ValueError("pool delivery content/version intent collision")
                pending[key] = row
                if not delivered_by:
                    continue
                issues.append(
                    {
                        "gate": "delivery",
                        "code": "DATA.POOL.VERSION_CONFLICT",
                        "ref": ref,
                    }
                )
            except (
                KeyError,
                OSError,
                ObjectTransactionError,
                TypeError,
                ValueError,
            ) as exc:
                issues.append(
                    {
                        "gate": "delivery",
                        "code": "DATA.POOL.DELIVERY_INTENT_INVALID",
                        "ref": f"{ref}:{exc}",
                    }
                )
    return (
        sorted(
            pending.values(),
            key=lambda row: (
                row["carrier"],
                row["contentId"],
                row["version"],
                row["intentRef"],
            ),
        ),
        sorted(issues, key=lambda row: (row["code"], row["ref"])),
    )


__all__ = ["inspect_pool_delivery_intents"]
