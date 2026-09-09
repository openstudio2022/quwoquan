"""只读 canonical 存在性、资格、引用闭包及候选图片唯一性；不选择 cohort。"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_selection import discover_explicit_cohort_candidates
from content.release.canonical.canonical_image_inventory import image_manifest_conflicts, readonly_image_inventory
from content.release.canonical.content_pool_record import is_pool_record_admitted
from content.release.canonical.effective_admission import effective_source_attribution_ready, resolve_effective_admission
from content.release.canonical.object_transaction_contract import ObjectTransactionError, _safe_rel
from content.release.canonical.pool_record_history import read_pool_record_history
from core.schema import validate_result
from core.publish_layout import logical_object_ref
from content.release.canonical.aggregate_release_closure import object_root

_CARRIERS = ("homepage", "article", "image", "video")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _code(exc: BaseException, default: str = "DATA.POOL.OBJECT_INVALID") -> str:
    value = str(exc).split(":", 1)[0].strip()
    return value if value.startswith("DATA.") else default


def _canonical_ref(value: str) -> str:
    if value.startswith("/entity/"):
        value = "entities/" + value.removeprefix("/entity/")
    relative = _safe_rel(value, label="poolQuery.objectRef")
    if relative.parts[0] not in {"posts", "entities"} or len(relative.parts) < 2:
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID: expected posts/ or entities/ exact objectRef")
    return relative.as_posix()


def _occupied_refs(publish_root: Path) -> list[str]:
    refs: set[str] = set()
    for prefix in ("entities", "posts"):
        root = publish_root / prefix
        for path in root.rglob("manifest.json"):
            if not {"sources", "records"} & set(path.relative_to(root).parts):
                refs.add(prefix + "/" + logical_object_ref(_read_json(path), prefix))
        for path in root.rglob("records"):
            if path.is_dir() and not (path.parent / "manifest.json").is_file():
                raise ObjectTransactionError("DATA.POOL.MANIFEST_MISSING")
    return sorted(refs)


def _illustrated_article_issue(publish_root: Path, post_ref: str) -> str:
    if not post_ref.startswith("article/"):
        return ""
    manifest = _read_json(object_root(publish_root, "posts", post_ref) / "manifest.json")
    if manifest.get("publishMediaMode") == "text_only":
        return ""
    covers = [asset for asset in manifest.get("assets") or [] if isinstance(asset, dict) and asset.get("role") == "cover"]
    return "" if len(covers) == 1 else f"illustrated article has {len(covers)} cover assets (needs exactly 1 cover)"


def _dependency_refs(manifest: Mapping[str, Any]) -> list[str]:
    return sorted({_canonical_ref(str(ref)) for ref in manifest.get("entityRefs") or []})


def _record_identity_fact(root: Path, *, homepage: bool) -> tuple[Mapping[str, Any] | None, list[str]]:
    record: Mapping[str, Any] | None = None
    errors: list[str] = []
    try:
        history = read_pool_record_history(root, object_type="homepage" if homepage else "content")
        record = history.records[-1] if history.records else None
        errors.extend(item.reason for item in history.exclusions if item.superseded_by is None)
        if record is None and not errors:
            errors.append("DATA.POOL.EXPLICIT_ADMISSION_MISSING")
    except (OSError, ValueError, ObjectTransactionError) as exc:
        errors.append(_code(exc))
    if errors:
        # 无效的最新 record 也占用身份；原始字节只作诊断，不授予资格。
        paths = sorted((root / "records").glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else -1)
        if paths:
            try:
                record = _read_json(paths[-1])
            except (OSError, ValueError):
                pass
    return record, errors


def _object_fact(publish_root: Path, ref: str) -> dict[str, Any]:
    kind, logical = ref.split("/", 1)
    root = object_root(publish_root, kind, logical)
    homepage = ref.startswith("entities/")
    occupied = root.exists() or root.is_symlink()
    row: dict[str, Any] = {
        "objectRef": ref, "objectId": None, "objectIds": [], "contentVersion": None,
        "carrier": "homepage" if homepage else ref.split("/")[1],
        "title": None, "occupied": occupied, "eligible": False,
        "state": "occupied" if occupied else "absent", "code": None,
        "dependencyRefs": [], "manifestIdentity": None, "recordIdentity": None,
    }
    if not row["occupied"]:
        row["code"] = "DATA.POOL.OBJECT_ABSENT"
        return row
    if any(path.is_symlink() for path in (root, *root.parents) if publish_root in path.parents):
        row.update(code="DATA.POOL.IDENTITY_STORAGE_INVALID", state="invalid")
        return row
    manifest: dict[str, Any] = {}
    errors: list[str] = []
    try:
        manifest = _read_json(root / "manifest.json")
        identity_key = "entityId" if homepage else "contentId"
        row["manifestIdentity"] = {"objectId": manifest.get(identity_key), "contentVersion": manifest.get("version")}
        row["title"] = manifest.get("title") or manifest.get("publishTitle") or manifest.get("displayName")
        row["dependencyRefs"] = _dependency_refs(manifest)
    except (OSError, ValueError, ObjectTransactionError) as exc:
        errors.append(_code(exc, "DATA.POOL.MANIFEST_INVALID"))
    record, record_errors = _record_identity_fact(root, homepage=homepage)
    errors.extend(record_errors)
    if record is not None:
        row["recordIdentity"] = {key: record.get(key) for key in ("objectId", "objectRef", "contentVersion", "recordSequence")}
    if manifest and (
        not (row["manifestIdentity"] or {}).get("objectId")
        or type(manifest.get("version")) is not int or manifest["version"] < 1
        or (homepage and manifest.get("entityRef") != "/entity/" + ref.removeprefix("entities/"))
        or (not homepage and manifest.get("contentType") != row["carrier"])
    ):
        errors.append("DATA.POOL.IDENTITY_INVALID")
    identities = [identity for identity in (row["manifestIdentity"], row["recordIdentity"]) if identity]
    row["objectIds"] = sorted({str(identity["objectId"]) for identity in identities if identity.get("objectId")})
    row["objectId"] = identities[0].get("objectId") if identities else None
    row["contentVersion"] = identities[0].get("contentVersion") if identities else None
    if len(row["objectIds"]) > 1 or (record is not None and (
        record.get("objectRef") != ref.split("/", 1)[1]
        or (manifest and record.get("contentVersion") != manifest.get("version"))
    )):
        errors.append("DATA.POOL.IDENTITY_INVALID")
    if not errors:
        try:
            admission = resolve_effective_admission(root, object_type="homepage" if homepage else "content", document=manifest)
            if not is_pool_record_admitted(admission.record):
                errors.append("DATA.POOL.OBJECT_NOT_ADMITTED")
            elif not effective_source_attribution_ready(admission):
                errors.append("DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE")
            if homepage:
                entity = manifest
                row["title"] = row["title"] or entity.get("label") or entity.get("name") or entity.get("displayName")
                if validate_result(entity, "publish", "entity"):
                    errors.append("DATA.POOL.ENTITY_SCHEMA_INVALID")
        except (OSError, ValueError, ObjectTransactionError) as exc:
            errors.append(_code(exc))
    row["code"] = errors[0] if errors else None
    row["state"] = "invalid" if errors else "occupied"
    return row


def _pool_facts(publish_root: Path, refs: Sequence[str]) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    pending = list(refs)
    while pending:
        ref = pending.pop()
        if ref in facts:
            continue
        facts[ref] = row = _object_fact(publish_root, ref)
        pending.extend(dep for dep in row["dependencyRefs"] if dep not in facts)
    # release 的既有 reader 继续拥有 Post 全闭包；保留其真实底层依赖错误。
    candidates, excluded = discover_explicit_cohort_candidates(
        publish_root=publish_root,
        post_refs=[ref.removeprefix("posts/") for ref, row in facts.items() if ref.startswith("posts/") and row["code"] is None],
    )
    candidate_refs = {f"posts/{candidate.post_ref}" for candidate in candidates}
    exclusions = {f"posts/{row.post_ref}": row.code for row in excluded}
    for ref, row in facts.items():
        if row["code"] is None and ref.startswith("entities/"):
            row.update(eligible=True, state="eligible")
    for ref, row in facts.items():
        if not ref.startswith("posts/") or row["code"] is not None:
            continue
        blocked = [facts[dep] for dep in row["dependencyRefs"] if not facts[dep]["eligible"]]
        if blocked:
            row["code"] = "DATA.POOL.REFERENCE_MISSING"
            row["dependencyIssues"] = [{"objectRef": dep["objectRef"], "code": dep["code"], "state": dep["state"]} for dep in blocked]
            row["deepestCode"] = blocked[0]["code"]
        else:
            row["code"] = exclusions.get(ref)
            if row["code"] is None and ref not in candidate_refs:
                row["code"] = "DATA.POOL.EXPLICIT_ADMISSION_MISSING"
            if row["code"] is None:
                detail = _illustrated_article_issue(publish_root, ref.removeprefix("posts/"))
                if detail:
                    row.update(code="DATA.POOL.ARTICLE_ILLUSTRATED_INCOMPLETE", detail=detail)
        row["eligible"] = row["code"] is None
        row["state"] = "eligible" if row["eligible"] else "invalid"
    for row in facts.values():
        row.setdefault("deepestCode", row["code"])
    return facts


def query_pool(publish_root: Path, *, target_refs: Sequence[str] | None = None, candidates: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """点名 targets/candidates 时仅查询这些对象及依赖；图片索引只打开一次。"""
    publish_root = publish_root.resolve()
    refs = set(_occupied_refs(publish_root) if target_refs is None and not candidates else map(_canonical_ref, target_refs or ()))
    for candidate in candidates:
        refs.add(_canonical_ref(str(candidate["objectRef"])))
        refs.update(_dependency_refs(candidate["manifest"]))
    facts = _pool_facts(publish_root, sorted(refs))
    results: list[dict[str, Any]] = []
    if candidates:
        with readonly_image_inventory(publish_root) as connection:
            for index, candidate in enumerate(candidates):
                ref = _canonical_ref(str(candidate["objectRef"]))
                manifest = candidate["manifest"]
                dependencies = _dependency_refs(manifest)
                peers = [{"objectRef": _canonical_ref(str(peer["objectRef"])), "manifest": peer["manifest"]}
                    for ordinal, peer in enumerate(candidates) if ordinal != index]
                conflicts = image_manifest_conflicts(connection, manifest=manifest, excluded_manifest_path=f"{ref}/manifest.json", candidate_peers=peers)
                results.append({"objectRef": ref, "occupied": facts[ref]["occupied"], "identity": facts[ref], "dependencyRefs": dependencies,
                    "dependencyIssues": [facts[dep] for dep in dependencies if not facts[dep]["eligible"]], "imageConflicts": conflicts})
    objects = sorted(facts.values(), key=lambda row: row["objectRef"])
    eligible = [row for row in objects if row["eligible"]]
    counts = Counter(row["carrier"] for row in eligible)
    return {
        "schema": "quwoquan_data.release_pool_query", "publishRoot": publish_root.as_posix(),
        "counts": {carrier: counts[carrier] for carrier in _CARRIERS},
        "eligible": {"homepages": [row["objectRef"] for row in eligible if row["carrier"] == "homepage"],
            "posts": [{**row, "entityRefs": row["dependencyRefs"]} for row in eligible if row["carrier"] != "homepage"]},
        "objects": objects, "occupied": [row for row in objects if row["occupied"]],
        "invalid": [row for row in objects if row["state"] == "invalid"],
        "excluded": [row for row in objects if not row["eligible"]], "preflight": results,
    }


__all__ = ["query_pool"]
