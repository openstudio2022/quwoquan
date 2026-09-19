"""内容池工作台的预热不可变快照、索引与离线文件台账。"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping
from urllib.parse import quote

from generated.semantic_document import CAPABILITY_IDS, ValidationCode, validate_envelope
from core.schema import assert_valid

KNOWN_RENDERERS = {"homepage", "article", "image", "video"}
VERSIONS = {"R0", "R1", "R2"}
MAX_EVIDENCE_BYTES = 1_048_576
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".html", ".htm", ".csv", ".xml"}
FILTER_METADATA_FIELDS = {
    "captureCoverages": "captureCoverage", "semanticParseCoverages": "semanticParseCoverage",
    "revisions": "revision", "captureMethods": "captureMethod", "dialectVersions": "dialectVersions",
    "semanticFingerprints": "semanticFingerprint", "lossSeverities": "lossSeverity",
    "carrierMismatches": "carrierMismatch", "modelBatches": "modelBatch", "reviewGates": "reviewGate",
}


class WorkbenchError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolved_dir(path: Path, *, create: bool = False) -> Path:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or path.is_symlink():
        raise WorkbenchError("CONTENT_WORKBENCH.ROOT_INVALID", f"not a real directory: {path}")
    return path.resolve(strict=True)


def validate_roots(publish: Path, workbench: Path, forbidden: list[Path] | None = None) -> tuple[Path, Path]:
    publish = _resolved_dir(publish)
    workbench = _resolved_dir(workbench, create=True)
    for other in [publish, *(forbidden or [])]:
        other = other.expanduser().resolve(strict=True)
        if _inside(workbench, other) or _inside(other, workbench):
            raise WorkbenchError("CONTENT_WORKBENCH.ROOT_OVERLAP", f"workbench root overlaps {other}")
    return publish, workbench


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def safe_relative(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise WorkbenchError("CONTENT_WORKBENCH.PATH_UNSAFE", "absolute, empty, or traversal path")
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise WorkbenchError("CONTENT_WORKBENCH.PATH_UNSAFE", "symlink is forbidden")
    try:
        resolved = cursor.resolve(strict=True)
    except FileNotFoundError as exc:
        raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "file not found", 404) from exc
    if not _inside(resolved, root.resolve(strict=True)):
        raise WorkbenchError("CONTENT_WORKBENCH.PATH_UNSAFE", "path escaped root")
    return resolved


def tree_digest(root: Path) -> str:
    """候选登记的唯一全字节摘要路径；canonical 快照不调用它。"""
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        if path.is_symlink():
            raise WorkbenchError("CONTENT_WORKBENCH.PATH_UNSAFE", "candidate contains symlink")
        relative = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big")); digest.update(relative)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path, code: str = "CONTENT_WORKBENCH.MANIFEST_INVALID") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON root must be an object")
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkbenchError(code, str(exc)) from exc


def _frontmatter(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"): return {"body": text}
    header, _, body = text[4:].partition("\n---\n")
    result: dict[str, Any] = {"body": body}
    for line in header.splitlines():
        if ":" not in line: continue
        key, value = line.split(":", 1); value = value.strip()
        if value.startswith("["):
            try: result[key.strip()] = json.loads(value.replace("'", '"'))
            except json.JSONDecodeError: result[key.strip()] = []
        else: result[key.strip()] = value.strip(" '\"")
    return result


def _manifest_dirs(root: Path) -> Iterator[Path]:
    for top in ("entities", "posts"):
        base = root / top
        if base.is_dir():
            for manifest in base.rglob("manifest.json"):
                if not manifest.is_symlink(): yield manifest.parent


def _taxonomy(root: Path) -> list[dict[str, Any]]:
    tags, nodes = root / "tags", {}
    if tags.is_dir():
        for definition in tags.rglob("_definition.json"):
            if definition.is_symlink(): continue
            ref = definition.parent.relative_to(tags).as_posix()
            try: raw = json.loads(definition.read_text())
            except (OSError, json.JSONDecodeError): raw = {}
            nodes[ref] = {"tagRef": ref, "label": raw.get("label", definition.parent.name), "children": []}
    roots = []
    for ref, node in sorted(nodes.items()):
        parent = ref.rpartition("/")[0]
        (nodes[parent]["children"] if parent in nodes else roots).append(node)
    return roots


def _content_file(directory: Path) -> tuple[dict[str, Any], str | None]:
    for relative in ("page.md", "article.md", "draft.article.md"):
        path = directory / relative
        if path.exists(): return _frontmatter(path), relative
    for path in sorted(directory.glob("*.json")):
        if path.name not in {"manifest.json", "content_review.json", "candidate.json"}:
            try: return json.loads(path.read_text()), path.name
            except (OSError, json.JSONDecodeError): continue
    return {}, None


def _existing_digest(raw: dict[str, Any], directory: Path) -> str | None:
    candidates = [raw.get("payloadDigest")]
    admission = raw.get("admission")
    if isinstance(admission, dict): candidates += [admission.get("payloadDigest"), admission.get("businessDigest")]
    records = directory / "records"
    if records.is_dir():
        for path in sorted(records.glob("*.json"), reverse=True):
            try:
                record = json.loads(path.read_text())
                candidates += [record.get("payloadDigest"), record.get("canonicalObjectDigest")]
            except (OSError, json.JSONDecodeError): pass
    return next((value for value in candidates if isinstance(value, str) and value.startswith("sha256:") and len(value) == 71), None)


def _metadata_digest(directory: Path, raw: dict[str, Any], content_path: str | None) -> str:
    """只摘要 manifest/content/review/source metadata，绝不读取 media。"""
    digest = hashlib.sha256()
    paths = [directory / "manifest.json", directory / "content_review.json"]
    if content_path: paths.append(directory / content_path)
    source_root = directory / "sources"
    if source_root.is_dir():
        paths.extend(source_root.glob("*/source.json")); paths.extend(source_root.glob("*/source.semantic.json"))
    for path in sorted(path for path in paths if path.is_file() and not path.is_symlink()):
        relative = path.relative_to(directory).as_posix().encode(); data = path.read_bytes()
        digest.update(relative); digest.update(b"\0"); digest.update(data); digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _is_cited(source_dir: Path, directory: Path, refs: list[str]) -> bool:
    prefix = source_dir.relative_to(directory).as_posix() + "/"
    return any(ref == prefix[:-1] or ref == prefix + "source.json" or ref.startswith(prefix) for ref in refs)


def _canonical_platform(source: dict[str, Any], canonical_url: str | None, fallback: Any) -> str:
    """平台来自 canonical source identity；展示 attribution 不得覆盖来源身份。"""
    identity = " ".join(str(source.get(key) or "") for key in ("sourceId", "sourceKind", "sourceClass")).casefold()
    host = ""
    if canonical_url:
        from urllib.parse import urlparse
        host = (urlparse(canonical_url).hostname or "").casefold()
    if "wikipedia" in identity or host.endswith("wikipedia.org"):
        return "Wikipedia"
    if "toutiao" in identity or host == "www.baike.com" or host.endswith(".baike.com"):
        return "头条百科"
    if "baidu" in identity or host == "baike.baidu.com":
        return "百度百科"
    return str(source.get("platform") or fallback or host or "未声明")


def _first_value(documents: list[dict[str, Any]], *keys: str, default: Any = None) -> Any:
    for document in documents:
        for key in keys:
            value = document.get(key)
            if value is not None:
                return value
    return default


def _semantic_candidates(directory: Path, raw: dict[str, Any]) -> tuple[Path | None, Path | None]:
    """只接受对象包内显式 sidecar；source AST 与产品 AST 不互相冒充。"""
    source_root = directory / "sources"
    source = next((path for path in sorted(source_root.glob("*/source.semantic.json")) if path.is_file() and not path.is_symlink()), None) if source_root.is_dir() else None
    target_names = []
    for key in ("semanticDocumentRef", "semanticDocumentPath", "semanticRef"):
        value = raw.get(key)
        if isinstance(value, str): target_names.append(value)
    target_names.extend(("semantic.document.json", "semantic_document.json", "semantic.json"))
    target = None
    for relative in target_names:
        try: candidate = safe_relative(directory, relative)
        except WorkbenchError: continue
        if candidate.is_file() and not candidate.is_symlink(): target = candidate; break
    return source, target or source


def _validated_semantic(path: Path | None, role: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if path is None:
        return None, {"code": f"CONTENT_WORKBENCH.{role.upper()}_MISSING", "detail": f"{role} semantic artifact is absent", "publishEligible": False}
    try:
        candidate = _read_json(path, "CONTENT_WORKBENCH.SEMANTIC_DOCUMENT_INVALID")
        validation = validate_envelope(candidate, CAPABILITY_IDS)
        if validation.code != ValidationCode.OK:
            return None, {"code": validation.code.value, "detail": validation.detail, "publishEligible": False}
        eligible = not any(node.get("disposition") in {"degraded", "unsupported_opaque", "blocked_unsafe"} for node in candidate.get("nodes", []) if isinstance(node, dict))
        return candidate, {"code": "ok", "detail": "", "publishEligible": eligible}
    except WorkbenchError as exc:
        return None, {"code": exc.code, "detail": str(exc), "publishEligible": False}


def _flatten_nodes(tree: dict[str, Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    def visit(node: Any) -> None:
        if not isinstance(node, dict): return
        result.append(node)
        for child in node.get("children", []): visit(child)
    if tree:
        for node in tree.get("nodes", []): visit(node)
    return result


def _anchor_key(node: dict[str, Any]) -> tuple[Any, ...] | None:
    anchor = node.get("sourceAnchor")
    if not isinstance(anchor, dict): return None
    return (anchor.get("origin"), anchor.get("start"), anchor.get("end"), anchor.get("selector"))


def _node_snapshot(node: dict[str, Any] | None) -> dict[str, Any] | None:
    if node is None: return None
    return {key: node.get(key) for key in ("nodeId", "kind", "sourceAnchor", "semanticFingerprint", "rawSlice", "attributes", "losses", "diagnostics") if key in node}


def _node_diff(source_tree: dict[str, Any] | None, target_tree: dict[str, Any] | None) -> list[dict[str, Any]]:
    source, target = _flatten_nodes(source_tree), _flatten_nodes(target_tree)
    by_id = {str(row.get("nodeId")): i for i, row in enumerate(target) if row.get("nodeId")}
    by_anchor = {_anchor_key(row): i for i, row in enumerate(target) if _anchor_key(row) is not None}
    used: set[int] = set(); rows = []
    for source_order, before in enumerate(source):
        target_order = by_id.get(str(before.get("nodeId")))
        aligned_by = "nodeId"
        if target_order is None or target_order in used:
            target_order = by_anchor.get(_anchor_key(before))
            aligned_by = "sourceAnchor"
        if target_order is None or target_order in used:
            same_order = target[source_order] if source_order < len(target) and source_order not in used else None
            target_order = source_order if same_order is not None and same_order.get("kind") == before.get("kind") else None
            aligned_by = "order"
        after = target[target_order] if target_order is not None else None
        if target_order is not None: used.add(target_order)
        disposition = str((after or {}).get("disposition") or "")
        if after is None: status = "missing"
        elif disposition == "blocked_unsafe": status = "blocked"
        elif disposition == "unsupported_opaque": status = "unsupported"
        elif disposition == "degraded": status = "degraded"
        elif before.get("semanticFingerprint") == after.get("semanticFingerprint"): status = "preserved"
        else: status = "normalized"
        losses = [x for owner in (before, after or {}) for x in owner.get("losses", []) if isinstance(x, dict)]
        diagnostics = [x for owner in (before, after or {}) for x in owner.get("diagnostics", []) if isinstance(x, dict)]
        rows.append({"alignmentStatus": status, "alignedBy": aligned_by if after is not None else "none", "nodeId": str((after or before).get("nodeId") or f"source-{source_order}"), "kind": str((after or before).get("kind") or "unknown"), "sourceOrder": source_order, "targetOrder": target_order, "orderingDelta": None if target_order is None else target_order-source_order, "sourceFingerprint": before.get("semanticFingerprint"), "targetFingerprint": after.get("semanticFingerprint") if after else None, "sourceAnchor": before.get("sourceAnchor"), "losses": losses, "diagnostics": diagnostics, "sourceNode": _node_snapshot(before), "targetNode": _node_snapshot(after)})
    for target_order, after in enumerate(target):
        if target_order not in used:
            rows.append({"alignmentStatus": "added", "alignedBy": "none", "nodeId": str(after.get("nodeId") or f"target-{target_order}"), "kind": str(after.get("kind") or "unknown"), "sourceOrder": None, "targetOrder": target_order, "orderingDelta": None, "sourceFingerprint": None, "targetFingerprint": after.get("semanticFingerprint"), "sourceAnchor": after.get("sourceAnchor"), "losses": [x for x in after.get("losses", []) if isinstance(x, dict)], "diagnostics": [x for x in after.get("diagnostics", []) if isinstance(x, dict)], "sourceNode": None, "targetNode": _node_snapshot(after)})
    return rows


def _canonical_governance(directory: Path, review: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dispositions = [dict(row, authority="canonical_content_review") for row in (review or {}).get("dispositions", []) if isinstance(row, dict)]
    decisions = []
    candidates = [directory / "semantic_human_decision.json", directory / "human_decision.json"]
    records = directory / "records"
    if records.is_dir(): candidates.extend(sorted(records.glob("*human*decision*.json")))
    for path in candidates:
        if not path.is_file() or path.is_symlink(): continue
        try:
            value = _read_json(path, "CONTENT_WORKBENCH.HUMAN_DECISION_INVALID")
            if value.get("schema") == "quwoquan_data.semantic_human_decision": decisions.append(dict(value, authority="canonical_human_decision"))
        except WorkbenchError:
            decisions.append({"authority": "canonical_human_decision", "readStatus": "unreadable", "path": path.relative_to(directory).as_posix()})
    return dispositions, decisions


def _semantic_metadata(raw: dict[str, Any], fields: dict[str, Any], directory: Path, review: dict[str, Any] | None) -> dict[str, Any]:
    source_path, target_path = _semantic_candidates(directory, raw)
    source_tree, source_validation = _validated_semantic(source_path, "source_semantic")
    target_tree, target_validation = _validated_semantic(target_path, "product_semantic")
    documents = [item for item in (target_tree, source_tree, raw.get("capture"), raw.get("semantic"), raw, fields, review) if isinstance(item, dict)]
    dialects = [str(value) for value in (_first_value(documents, "dialectVersions", "dialects", default=[]) or [])]
    for value in (_first_value(documents, "dialectVersion"), _first_value(documents, "markdownDialect")):
        if value and str(value) not in dialects: dialects.append(str(value))
    dispositions: dict[str, int] = defaultdict(int); diagnostics: list[Any] = []; losses: list[Any] = []
    for node in _flatten_nodes(target_tree):
        dispositions[str(node.get("disposition") or "unknown")] += 1
        diagnostics.extend(row for row in node.get("diagnostics", []) if isinstance(row, dict)); losses.extend(row for row in node.get("losses", []) if isinstance(row, dict))
    if target_tree: losses.extend(row for row in target_tree.get("losses", []) if isinstance(row, dict))
    diagnostics.extend(losses)
    severity_order = {"unknown": 0, "none": 0, "info": 0, "low": 1, "warning": 1, "medium": 2, "high": 3, "error": 3, "critical": 4}
    severities = [str(row.get("severity") or "warning") for row in losses if isinstance(row, dict)]
    review_gate = _first_value(documents, "reviewGate", "gate", default={}); review_gate = review_gate if isinstance(review_gate, dict) else {"decision": str(review_gate)}
    source_profile = _first_value(documents, "sourceProfile", default={}); source_profile = source_profile if isinstance(source_profile, dict) else {}
    canonical_dispositions, canonical_decisions = _canonical_governance(directory, review)
    return {"captureCoverage": _first_value(documents, "captureCoverage"), "semanticParseCoverage": _first_value(documents, "semanticParseCoverage"), "revision": str(_first_value([source_profile, *documents], "revision", "revisionId", "captureRevision", default="unknown")), "captureMethod": str(_first_value(documents, "captureMethod", "extractor", "method", default="unknown")), "dialectVersions": dialects, "semanticFingerprint": target_tree.get("semanticFingerprint") if target_tree else None, "dispositionCounts": dict(dispositions), "lossSeverity": max(severities, key=lambda value: severity_order.get(value, 0), default="none"), "carrierMismatch": bool(_first_value(documents, "carrierMismatch", default=False)), "modelBatch": str(_first_value(documents, "modelBatch", "modelBatchId", default="unknown")), "reviewGate": review_gate, "sourceSemanticTree": source_tree, "semanticTree": target_tree, "sourceSemanticValidation": source_validation, "semanticValidation": target_validation, "nodeDiagnostics": diagnostics, "nodeDiff": _node_diff(source_tree, target_tree), "canonicalDispositions": canonical_dispositions, "canonicalHumanDecisions": canonical_decisions}


def _source_descriptors(raw: dict[str, Any], directory: Path) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    refs = [str(value) for value in raw.get("citedSourceRefs", []) if isinstance(value, str)]
    descriptors, evidence_locators = [], {}
    sources_root = directory / "sources"
    if sources_root.is_dir():
        for source_json in sorted(sources_root.glob("*/source.json")):
            if source_json.is_symlink() or source_json.parent.is_symlink(): continue
            source = _read_json(source_json, "CONTENT_WORKBENCH.SOURCE_INVALID")
            prefix = source_json.parent.relative_to(directory).as_posix() + "/"
            adopted = _is_cited(source_json.parent, directory, refs) or source.get("sourceUseMode") in {"licensed_adaptation", "factual_reference_only"}
            if not adopted: continue
            source_id = str(source.get("sourceId") or source_json.parent.name)
            rows = [row for row in source.get("evidence", []) if isinstance(row, dict)]
            ranked = sorted(rows, key=lambda row: (0 if prefix + str(row.get("path")) in refs and Path(str(row.get("path", ""))).suffix.lower() in {".md", ".markdown"} else 1 if row.get("kind") == "source_excerpt" else 2 if row.get("kind") == "source_snapshot" and Path(str(row.get("path", ""))).suffix.lower() in TEXT_SUFFIXES else 3, str(row.get("path", ""))))
            evidence_rows = []
            for number, row in enumerate(ranked, 1):
                relative = str(row.get("path", "")); evidence_id = str(row.get("evidenceId") or f"e{number:03d}")
                declared_digest = row.get("sha256")
                digest_valid = isinstance(declared_digest, str) and len(declared_digest) == 71 and declared_digest.startswith("sha256:")
                evidence_path = source_json.parent / relative
                exists = bool(relative) and evidence_path.is_file() and not evidence_path.is_symlink()
                media_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
                textual = Path(relative).suffix.lower() in TEXT_SUFFIXES
                read_status = "available" if exists and digest_valid else "missing" if not exists else "descriptor_invalid"
                display_mode = ("source-gfm" if Path(relative).suffix.lower() in {".md", ".markdown"} else "raw") if textual and read_status == "available" else "unavailable"
                descriptor = {"evidenceId": evidence_id, "kind": str(row.get("kind") or "unknown"), "mediaType": media_type, "sha256": declared_digest if digest_valid else None, "bytes": int(row.get("bytes") or 0), "displayMode": display_mode, "defaultReason": None if display_mode != "unavailable" else read_status, "readStatus": read_status, "revision": row.get("revision") or source.get("revision") or source.get("sourceRevision")}
                evidence_rows.append(descriptor)
                if read_status == "available": evidence_locators[(source_id, evidence_id)] = {"directory": source_json.parent, "entry": {**row, "path": relative}, "descriptor": descriptor}
            attribution = source.get("sourceAttribution") if isinstance(source.get("sourceAttribution"), dict) else {}
            metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
            source_url = source.get("sourceUrl")
            canonical_url = source_url if isinstance(source_url, str) and source_url.startswith("https://") else None
            platform = _canonical_platform(source, canonical_url, metadata.get("platform") or attribution.get("platform"))
            descriptors.append({"sourceUnitId": source_id, "title": str(metadata.get("title") or attribution.get("attributionText") or source_id), "platform": platform, "canonicalUrl": canonical_url, "sourceUseMode": str(source.get("sourceUseMode") or "unknown"), "rightsClue": str(attribution.get("rightsBasis") or metadata.get("license") or "unknown"), "fetchedAt": str(source.get("fetchedAt") or "unknown"), "evidenceState": "available" if any(row["readStatus"] == "available" for row in evidence_rows) else "missing" if any(row["readStatus"] == "missing" for row in evidence_rows) or not rows else "unreadable", "adopted": True, "evidence": evidence_rows, "defaultEvidenceId": next((row["evidenceId"] for row in evidence_rows if row["displayMode"] != "unavailable"), None)})
    if not descriptors:
        attribution = raw.get("sourceAttribution")
        if isinstance(attribution, dict):
            descriptors.append({"sourceUnitId": "sourceAttribution", "title": str(attribution.get("attributionText") or attribution.get("platform") or "sourceAttribution"), "platform": str(attribution.get("platform") or "未声明"), "canonicalUrl": attribution.get("sourcePostUrl") if isinstance(attribution.get("sourcePostUrl"), str) and attribution.get("sourcePostUrl").startswith("https://") else None, "sourceUseMode": "attribution_record_only", "rightsClue": str(attribution.get("rightsBasis") or "unknown"), "fetchedAt": "unknown", "evidenceState": "missing", "adopted": True, "evidence": [], "defaultEvidenceId": None})
        else: descriptors.append({"sourceUnitId": "undeclared", "title": "未声明", "platform": "未声明", "canonicalUrl": None, "sourceUseMode": "unknown", "rightsClue": "unknown", "fetchedAt": "unknown", "evidenceState": "missing", "adopted": True, "evidence": [], "defaultEvidenceId": None})
    return descriptors, evidence_locators


def _media_entries(raw: dict[str, Any], directory: Path, object_id: str, version_id: str) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    entries, locators, seen = [], {}, set()
    for asset in raw.get("assets", []):
        if not isinstance(asset, dict): continue
        relative = asset.get("fileName") or asset.get("path")
        if relative and not str(relative).startswith("media/"): relative = f"media/{relative}"
        path = directory / str(relative) if relative else None
        if not relative or not path or not path.is_file() or path.is_symlink(): continue
        relative = str(relative); seen.add(relative); locators[relative] = path
        entries.append({"relativePath": relative, "url": f"/api/media/{quote(object_id, safe='')}/{quote(version_id, safe='')}/{quote(relative, safe='/')}", "mime": asset.get("mimeType"), "alt": asset.get("caption") or raw.get("title")})
    media_root = directory / "media"
    if media_root.is_dir():
        for path in sorted(item for item in media_root.rglob("*") if item.is_file() and not item.is_symlink()):
            relative = path.relative_to(directory).as_posix()
            if relative in seen: continue
            locators[relative] = path
            entries.append({"relativePath": relative, "url": f"/api/media/{quote(object_id, safe='')}/{quote(version_id, safe='')}/{quote(relative, safe='/')}", "mime": mimetypes.guess_type(path.name)[0], "alt": raw.get("title")})
    return entries, locators


def _extract_object(directory: Path, root: Path, version: str, review: dict[str, Any] | None = None, parent: str | None = None, canonical: bool = False) -> dict[str, Any]:
    raw = _read_json(directory / "manifest.json")
    fields, content_path = _content_file(directory)
    relative = directory.relative_to(root).as_posix() if _inside(directory, root) else str(raw.get("objectRef", directory.name))
    object_id = str(raw.get("contentId") or raw.get("entityId") or raw.get("objectId") or relative)
    form = str(raw.get("contentFormId") or raw.get("carrier") or raw.get("contentType") or ("homepage" if relative.startswith("entities/") else "unknown"))
    tags = list(raw.get("tagRefs") or fields.get("tagRefs") or [])
    source_facts, source_evidence = _source_descriptors(raw, directory)
    text_bytes = sum(path.stat().st_size for path in directory.iterdir() if path.is_file() and path.suffix in {".md", ".txt", ".json"})
    media_root = directory / "media"
    media_bytes = sum(path.stat().st_size for path in media_root.rglob("*") if path.is_file()) if media_root.is_dir() else 0
    media, media_locators = _media_entries(raw, directory, object_id, version)
    production_review = review
    if production_review is None and (directory / "content_review.json").is_file():
        try: production_review = _read_json(directory / "content_review.json")
        except WorkbenchError: production_review = {"status": "unreadable"}
    semantic = _semantic_metadata(raw, fields, directory, production_review)
    result = {"objectId": object_id, "objectRef": relative, "versionId": version, "businessDigest": (_existing_digest(raw, directory) or _metadata_digest(directory, raw, content_path)) if canonical else tree_digest(directory), "contentFormId": form, "title": str(raw.get("title") or fields.get("title") or directory.name), "tagRefs": tags, "sources": sorted({str(f["platform"]) for f in source_facts}), "reviewState": (review or {}).get("decision", "pending_review"), "poolState": "published" if version == "R0" else "offline_candidate", "rendererHint": {"kind": form if form in KNOWN_RENDERERS else "generic", "known": form in KNOWN_RENDERERS}, "textBytes": text_bytes, "mediaBytes": media_bytes, **{key: semantic[key] for key in ("captureCoverage", "semanticParseCoverage", "revision", "captureMethod", "dialectVersions", "semanticFingerprint", "dispositionCounts", "lossSeverity", "carrierMismatch", "modelBatch", "reviewGate")}, "_directory": directory, "_raw": raw, "_fields": fields, "_contentPath": content_path, "_sourceFacts": source_facts, "_sourceEvidence": source_evidence, "_media": media, "_mediaLocators": media_locators, "_sourceSemanticTree": semantic["sourceSemanticTree"], "_semanticTree": semantic["semanticTree"], "_sourceSemanticValidation": semantic["sourceSemanticValidation"], "_semanticValidation": semantic["semanticValidation"], "_nodeDiagnostics": semantic["nodeDiagnostics"], "_nodeDiff": semantic["nodeDiff"], "_canonicalDispositions": semantic["canonicalDispositions"], "_canonicalHumanDecisions": semantic["canonicalHumanDecisions"]}
    if parent: result["parentVersionId"] = parent
    return result


def _descendants(tree: list[dict[str, Any]]) -> dict[str, frozenset[str]]:
    result = {}
    def walk(node):
        own = {node["tagRef"]}
        for child in node["children"]: own |= walk(child)
        result[node["tagRef"]] = frozenset(own); return own
    for node in tree: walk(node)
    return result


@dataclass(frozen=True)
class SnapshotState:
    token: str
    items: tuple[dict[str, Any], ...]
    taxonomy: tuple[dict[str, Any], ...]
    descendants: Mapping[str, frozenset[str]]
    locators: Mapping[tuple[str, str], dict[str, Any]]
    inverted: Mapping[str, Mapping[str, frozenset[int]]]
    media: Mapping[tuple[str, str, str], Path]
    evidence: Mapping[tuple[str, str, str], dict[str, Any]]
    lineage: Mapping[str, tuple[dict[str, Any], ...]]
    reviews: Mapping[tuple[str, str], dict[str, Any]]
    quality: tuple[dict[str, Any], ...]
    built_at: float
    build_ms: float


class WorkbenchService:
    def __init__(self, publish_root: Path, workbench_root: Path, *, forbidden_roots: list[Path] | None = None, staging_root: Path | None = None):
        forbidden = list(forbidden_roots or [])
        if staging_root: forbidden.append(staging_root)
        self.publish_root, self.workbench_root = validate_roots(publish_root, workbench_root, forbidden)
        self.staging_root = _resolved_dir(staging_root) if staging_root else None
        for name in ("reviews", "candidates", "locks"): (self.workbench_root / name).mkdir(exist_ok=True)
        self._state_lock, self._refresh_lock = threading.Lock(), threading.Lock()
        self._refreshing = False; self._build_count = 0
        self._state = self._build_snapshot()

    @staticmethod
    def _clean(item): return {k: v for k, v in item.items() if not k.startswith("_")}

    def _reviews(self):
        result = {}
        for path in (self.workbench_root / "reviews").glob("*.json"):
            try:
                record = json.loads(path.read_text()); result[(record["objectId"], record["versionId"])] = record
            except (OSError, json.JSONDecodeError, KeyError) as exc: raise WorkbenchError("CONTENT_WORKBENCH.LEDGER_CORRUPT", str(exc), 500) from exc
        return result

    def _make_state(self, items: list[dict[str, Any]], taxonomy: list[dict[str, Any]], started: float) -> SnapshotState:
        items.sort(key=lambda x: (x["objectId"], x["versionId"]))
        public = [self._clean(x) for x in items]; token = digest_bytes(canonical_json(public))
        inverted: dict[str, dict[str, set[int]]] = {f: defaultdict(set) for f in ("contentFormId", "versionId", "reviewState", "poolState", "sources", "tagRefs", *FILTER_METADATA_FIELDS.values())}
        locators, media, evidence, lineage = {}, {}, {}, defaultdict(list)
        for index, item in enumerate(items):
            item["_index"] = index
            key = (item["objectId"], item["versionId"]); locators[key] = item
            for field in inverted:
                values = item[field] if isinstance(item[field], list) and field not in {"dialectVersions", "sources", "tagRefs"} else item[field] if isinstance(item[field], list) else [item[field]]
                for value in values:
                    facet_value = canonical_json(value).decode() if isinstance(value, (dict, list)) else str(value).lower() if isinstance(value, bool) else str(value)
                    inverted[field][facet_value].add(index)
            for relative, path in item["_mediaLocators"].items(): media[key + (relative,)] = path
            for (source_id, evidence_id), entry in item["_sourceEvidence"].items(): evidence[key + (source_id, evidence_id)] = entry
            lineage[item["objectId"]].append({"versionId": item["versionId"], "parentVersionId": item.get("parentVersionId"), "businessDigest": item["businessDigest"], "reviewState": item["reviewState"]})
        frozen_inv = MappingProxyType({f: MappingProxyType({v: frozenset(ids) for v, ids in values.items()}) for f, values in inverted.items()})
        reviews = MappingProxyType(self._reviews())
        quality = tuple(self._quality_summary(items))
        return SnapshotState(token, tuple(items), tuple(taxonomy), MappingProxyType(_descendants(taxonomy)), MappingProxyType(locators), frozen_inv, MappingProxyType(media), MappingProxyType(evidence), MappingProxyType({k: tuple(v) for k, v in lineage.items()}), reviews, quality, time.time(), (time.perf_counter() - started) * 1000)

    def _build_snapshot(self) -> SnapshotState:
        started = time.perf_counter(); reviews = self._reviews(); items = []
        for directory in _manifest_dirs(self.publish_root):
            item = _extract_object(directory, self.publish_root, "R0", reviews.get(("", "")), canonical=True)
            item["reviewState"] = reviews.get((item["objectId"], "R0"), {}).get("decision", "pending_review"); items.append(item)
        for metadata in (self.workbench_root / "candidates").glob("*/R[12]/candidate.json"):
            candidate = _read_json(metadata, "CONTENT_WORKBENCH.LEDGER_CORRUPT"); directory = metadata.parent / "business"
            item = _extract_object(directory, directory, candidate["versionId"], reviews.get((candidate["objectId"], candidate["versionId"])), candidate["parentVersionId"])
            item.update(objectId=candidate["objectId"], objectRef=candidate["candidateRef"], businessDigest=candidate["businessDigest"]); items.append(item)
        self._build_count += 1
        return self._make_state(items, _taxonomy(self.publish_root), started)

    def snapshot(self):
        state = self._state
        return state.token, list(state.items), list(state.taxonomy)

    def startup_stats(self):
        state = self._state
        return {"readToken": state.token, "objects": len(state.items), "mediaLocators": len(state.media), "evidenceLocators": len(state.evidence), "buildMs": round(state.build_ms, 3), "buildCount": self._build_count}

    def refresh(self):
        if not self._refresh_lock.acquire(blocking=False): raise WorkbenchError("CONTENT_WORKBENCH.REFRESH_IN_PROGRESS", "refresh already in progress", 409)
        self._refreshing = True
        try:
            new_state = self._build_snapshot()
            with self._state_lock: self._state = new_state
            return {"readToken": new_state.token, "stale_read": False, "refreshed": True}
        finally:
            self._refreshing = False; self._refresh_lock.release()

    @staticmethod
    def _validate_filters(filters):
        try:
            assert_valid(
                filters,
                "governance",
                "content_workbench/workbench_filter",
                label="content workbench filter",
            )
        except ValueError as exc:
            raise WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", str(exc)) from exc
        if filters.get("tagMatch", "subtree") not in {"direct", "subtree"}: raise WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", "tagMatch must be direct or subtree")
        if filters.get("sort", "updated_desc") not in {"updated_desc", "title_asc", "form_asc", "object_asc"}: raise WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", "invalid sort")
        if not isinstance(filters.get("page", 1), int) or filters.get("page", 1) < 1: raise WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", "page must be >= 1")
        if not isinstance(filters.get("pageSize", 20), int) or not 1 <= filters.get("pageSize", 20) <= 100: raise WorkbenchError("CONTENT_WORKBENCH.REQUEST_INVALID", "pageSize must be between 1 and 100")

    def _read(self, filters=None):
        effective = filters or {}; self._validate_filters(effective); state = self._state
        if effective.get("readToken") and effective["readToken"] != state.token: raise WorkbenchError("CONTENT_WORKBENCH.STALE_READ", "readToken does not match the current snapshot", 409)
        return state, self._refreshing

    def _filter_ids(self, state, filters=None):
        effective = filters or {}; ids = set(range(len(state.items)))
        for key, field in (("contentFormIds", "contentFormId"), ("versions", "versionId"), ("reviewStates", "reviewState"), ("poolStates", "poolState"), ("sources", "sources"), *FILTER_METADATA_FIELDS.items()):
            if effective.get(key): ids &= set().union(*(state.inverted[field].get(str(v), frozenset()) for v in effective[key]))
        if effective.get("tagRefs"):
            wanted = set(effective["tagRefs"]) if effective.get("tagMatch", "subtree") == "direct" else set().union(*(state.descendants.get(v, frozenset({v})) for v in effective["tagRefs"]))
            ids &= set().union(*(state.inverted["tagRefs"].get(v, frozenset()) for v in wanted))
        query = str(effective.get("query", "")).strip().casefold()
        if query: ids = {i for i in ids if query in " ".join((state.items[i]["title"], state.items[i]["objectId"], state.items[i]["objectRef"])).casefold()}
        return ids

    @staticmethod
    def _sort(items, sort):
        if sort == "title_asc": return sorted(items, key=lambda x: (x["title"].casefold(), x["objectId"], x["versionId"]))
        if sort == "form_asc": return sorted(items, key=lambda x: (x["contentFormId"], x["title"].casefold(), x["objectId"]))
        if sort == "object_asc": return sorted(items, key=lambda x: (x["objectId"], x["versionId"]))
        return sorted(items, key=lambda x: (x["objectId"], x["versionId"]), reverse=True)

    def query(self, filters=None):
        effective = filters or {}; state, stale = self._read(effective); selected = self._sort([state.items[i] for i in self._filter_ids(state, effective)], effective.get("sort", "updated_desc")); page, size = effective.get("page", 1), effective.get("pageSize", 20); start = (page - 1) * size
        return {"readToken": state.token, "stale_read": stale, "total": len(selected), "page": page, "pageSize": size, "items": [self._clean(x) for x in selected[start:start + size]]}

    def _taxonomy_counts(self, state, ids):
        def annotate(node):
            wanted = state.descendants[node["tagRef"]]; matched = set().union(*(state.inverted["tagRefs"].get(v, frozenset()) for v in wanted))
            return {**node, "count": len(ids & matched), "children": [annotate(c) for c in node["children"]]}
        return [annotate(n) for n in state.taxonomy]

    def _counts(self, state, ids, field):
        return [{"value": value, "count": len(ids & set(indexes))} for value, indexes in sorted(state.inverted[field].items())]

    def facets(self, filters=None):
        state, stale = self._read(filters); ids = self._filter_ids(state, filters)
        return {"readToken": state.token, "stale_read": stale, "total": len(ids), "facets": {"contentForms": self._counts(state, ids, "contentFormId"), "sources": self._counts(state, ids, "sources"), "versions": self._counts(state, ids, "versionId"), "reviewStates": self._counts(state, ids, "reviewState"), "poolStates": self._counts(state, ids, "poolState"), **{key: self._counts(state, ids, field) for key, field in FILTER_METADATA_FIELDS.items()}}, "taxonomy": self._taxonomy_counts(state, ids)}

    @staticmethod
    def _quality_summary(items):
        values = defaultdict(list)
        for item in items:
            path = item["_directory"] / "content_review.json"
            if not path.exists(): continue
            try: scores = json.loads(path.read_text()).get("qualityScores", {})
            except (OSError, json.JSONDecodeError): continue
            if isinstance(scores, dict):
                for dimension, score in scores.items():
                    if isinstance(score, int) and 1 <= score <= 5: values[(item["contentFormId"], dimension)].append(score)
        return [{"contentFormId": form, "dimension": dimension, "n": len(scores), "mean": sum(scores) / len(scores), "distribution": {str(v): scores.count(v) for v in range(1, 6)}} for (form, dimension), scores in sorted(values.items())]

    def overview(self, filters=None):
        state, stale = self._read(filters); ids = self._filter_ids(state, filters); selected = [state.items[i] for i in ids]
        return {"readToken": state.token, "stale_read": stale, "total": len(ids), "contentForms": [{"contentFormId": form, "rendererHint": {"kind": form if form in KNOWN_RENDERERS else "generic", "known": form in KNOWN_RENDERERS}, "count": len(ids & set(indexes))} for form, indexes in sorted(state.inverted["contentFormId"].items())], "reviewStates": self._counts(state, ids, "reviewState"), "sources": self._counts(state, ids, "sources"), "taxonomy": self._taxonomy_counts(state, ids), "volume": {"textBytes": sum(x["textBytes"] for x in selected), "mediaBytes": sum(x["mediaBytes"] for x in selected)}, "qualityScores": self._quality_summary(selected) if len(ids) != len(state.items) else list(state.quality)}

    def detail(self, object_id, version_id, filters=None):
        state, stale = self._read(filters); found = state.locators.get((object_id, version_id))
        constrained = any(key in (filters or {}) for key in ("contentFormIds", "versions", "reviewStates", "poolStates", "sources", "tagRefs", "query", *FILTER_METADATA_FIELDS.keys()))
        if found is None or (constrained and found["_index"] not in self._filter_ids(state, filters)): raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "object version not found", 404)
        review_path = found["_directory"] / "content_review.json"
        try: production = json.loads(review_path.read_text()) if review_path.exists() else None
        except json.JSONDecodeError: production = {"status": "unreadable"}
        return {"readToken": state.token, "stale_read": stale, "item": self._clean(found), "body": found["_fields"].get("body"), "fields": found["_fields"], "raw": found["_raw"], "media": found["_media"], "sourceDescriptors": found["_sourceFacts"], "productionReview": production, "humanReview": state.reviews.get((object_id, version_id)), "lineage": list(state.lineage.get(object_id, ())), "qualityScores": production.get("qualityScores") if isinstance(production, dict) else None, "sourceSemanticTree": found["_sourceSemanticTree"], "semanticTree": found["_semanticTree"], "sourceSemanticValidation": found["_sourceSemanticValidation"], "semanticValidation": found["_semanticValidation"], "nodeDiagnostics": found["_nodeDiagnostics"], "nodeDiff": found["_nodeDiff"], "canonicalDispositions": found["_canonicalDispositions"], "canonicalHumanDecisions": found["_canonicalHumanDecisions"], "offlineSuggestion": dict(state.reviews.get((object_id, version_id)), authority="workbench_offline_suggestion") if state.reviews.get((object_id, version_id)) else None}

    def media_path(self, object_id, version_id, relative, read_token=None):
        state, _ = self._read({"readToken": read_token} if read_token else None)
        path = state.media.get((object_id, version_id, relative))
        if path is None: raise WorkbenchError("CONTENT_WORKBENCH.NOT_FOUND", "media not found", 404)
        return path

    def source_evidence(self, object_id, version_id, source_id, evidence_id, read_token=None):
        state, stale = self._read({"readToken": read_token} if read_token else None)
        locator = state.evidence.get((object_id, version_id, source_id, evidence_id))
        if locator is None: raise WorkbenchError("CONTENT_WORKBENCH.SOURCE_EVIDENCE_NOT_FOUND", "source evidence not found", 404)
        entry = locator["entry"]; relative = str(entry.get("path", "")); path = safe_relative(locator["directory"], relative)
        if not path.is_file(): raise WorkbenchError("CONTENT_WORKBENCH.SOURCE_EVIDENCE_NOT_FOUND", "source evidence is not a file", 404)
        suffix = path.suffix.lower(); mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if suffix not in TEXT_SUFFIXES or (not mime.startswith("text/") and mime not in {"application/json", "application/xml"}): raise WorkbenchError("CONTENT_WORKBENCH.SOURCE_EVIDENCE_NON_TEXT", "source evidence is not textual", 415)
        size = path.stat().st_size
        if size > MAX_EVIDENCE_BYTES: raise WorkbenchError("CONTENT_WORKBENCH.SOURCE_EVIDENCE_TOO_LARGE", "source evidence exceeds size limit", 413)
        data = path.read_bytes()
        if entry.get("bytes") is not None and entry["bytes"] != len(data): raise WorkbenchError("CONTENT_WORKBENCH.SOURCE_EVIDENCE_DIGEST_MISMATCH", "source evidence byte count mismatch", 409)
        if entry.get("sha256") and entry["sha256"] != digest_bytes(data): raise WorkbenchError("CONTENT_WORKBENCH.SOURCE_EVIDENCE_DIGEST_MISMATCH", "source evidence digest mismatch", 409)
        try: content = data.decode("utf-8")
        except UnicodeDecodeError as exc: raise WorkbenchError("CONTENT_WORKBENCH.SOURCE_EVIDENCE_UTF8_INVALID", "source evidence is not UTF-8", 422) from exc
        return {"readToken": state.token, "stale_read": stale, "sourceUnitId": source_id, "evidenceId": evidence_id, "kind": str(entry.get("kind") or "unknown"), "mediaType": mime, "bytes": size, "sha256": digest_bytes(data), "truncated": False, "content": content}

    @contextmanager
    def _lock(self, object_id):
        path = self.workbench_root / "locks" / (hashlib.sha256(object_id.encode()).hexdigest() + ".lock")
        try: descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc: raise WorkbenchError("CONTENT_WORKBENCH.LOCK_CONFLICT", "object is locked", 409) from exc
        try: os.write(descriptor, str(os.getpid()).encode()); os.close(descriptor); yield
        finally:
            try: path.unlink()
            except FileNotFoundError: pass

    def _atomic_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True); descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle: handle.write(canonical_json(payload)); handle.flush(); os.fsync(handle.fileno())
            json.loads(Path(temporary).read_text()); os.replace(temporary, path)
        finally:
            try: Path(temporary).unlink()
            except FileNotFoundError: pass

    def _replace_item(self, key, replacement):
        started = time.perf_counter(); items = [x for x in self._state.items if (x["objectId"], x["versionId"]) != key]
        if replacement is not None: items.append(replacement)
        with self._state_lock: self._state = self._make_state(items, list(self._state.taxonomy), started)

    def save_review(self, data):
        object_id, version_id, decision = str(data.get("objectId", "")), str(data.get("versionId", "")), data.get("decision")
        if version_id not in VERSIONS or decision not in {"qualified", "unqualified"}: raise WorkbenchError("CONTENT_WORKBENCH.REVIEW_INVALID", "invalid version or decision")
        changes, target = data.get("changes"), str(data.get("targetState", "")).strip()
        if decision == "unqualified" and (not isinstance(changes, list) or not changes or any(not str(x).strip() for x in changes) or not target): raise WorkbenchError("CONTENT_WORKBENCH.REVIEW_INVALID", "unqualified requires non-empty changes and targetState")
        current = self.detail(object_id, version_id)["item"]
        if data.get("businessDigest") != current["businessDigest"]: raise WorkbenchError("CONTENT_WORKBENCH.VERSION_CONFLICT", "business digest mismatch", 409)
        business = {k: data.get(k) for k in ("objectId", "versionId", "businessDigest", "decision", "changes", "targetState")}; record_digest = digest_bytes(canonical_json(business)); identity = hashlib.sha256(f"{object_id}:{version_id}".encode()).hexdigest(); path = self.workbench_root / "reviews" / f"{identity}.json"
        with self._lock(object_id):
            previous = json.loads(path.read_text()) if path.exists() else None
            if previous and previous["recordDigest"] == record_digest:
                item = self._state.locators[(object_id, version_id)]
                return {**previous, "readToken": self._state.token, "stale_read": False, "item": self._clean(item)}
            record = {k: data[k] for k in ("objectId", "versionId", "businessDigest", "decision")}
            if decision == "unqualified": record.update(changes=changes, targetState=target)
            record.update(revision=int(previous.get("revision", 0)) + 1 if previous else 1, previousDigest=previous.get("recordDigest") if previous else None, recordDigest=record_digest)
            try:
                assert_valid(
                    record,
                    "governance",
                    "content_workbench/offline_review",
                    label="content workbench offline review",
                )
            except ValueError as exc:
                raise WorkbenchError("CONTENT_WORKBENCH.REVIEW_INVALID", str(exc)) from exc
            if previous:
                archive = self.workbench_root / "reviews" / "records" / identity / f"{previous['revision']:06d}-{previous['recordDigest'][7:]}.json"
                if not archive.exists(): self._atomic_json(archive, previous)
            self._atomic_json(path, record)
        item = dict(self._state.locators[(object_id, version_id)]); item["reviewState"] = decision; self._replace_item((object_id, version_id), item)
        return {**record, "readToken": self._state.token, "stale_read": False, "item": self._clean(item)}

    def register_candidate(self, data):
        if not self.staging_root: raise WorkbenchError("CONTENT_WORKBENCH.STAGING_REQUIRED", "staging root is required")
        object_id, parent, target = str(data.get("objectId", "")), str(data.get("parentVersionId", "")), str(data.get("versionId", ""))
        if (parent, target) not in {("R0", "R1"), ("R1", "R2")}: raise WorkbenchError("CONTENT_WORKBENCH.CANDIDATE_INVALID", "only R0→R1 and R1→R2 are allowed")
        if self.detail(object_id, parent)["item"]["reviewState"] == "pending_review": raise WorkbenchError("CONTENT_WORKBENCH.PARENT_REVIEW_REQUIRED", "parent must be reviewed", 409)
        source = safe_relative(self.staging_root, str(data.get("sourcePath", "")))
        if not source.is_dir(): raise WorkbenchError("CONTENT_WORKBENCH.CANDIDATE_INVALID", "sourcePath must be a directory")
        business_digest = tree_digest(source); object_hash = hashlib.sha256(object_id.encode()).hexdigest(); object_dir = self.workbench_root / "candidates" / object_hash; destination = object_dir / target; metadata = destination / "candidate.json"
        record_digest = digest_bytes(canonical_json({"objectId": object_id, "parentVersionId": parent, "versionId": target, "businessDigest": business_digest}))
        with self._lock(object_id):
            if metadata.exists():
                old = json.loads(metadata.read_text())
                if old["recordDigest"] == record_digest:
                    item = self._state.locators.get((object_id, target))
                    return {**old, "readToken": self._state.token, "stale_read": False, "item": self._clean(item) if item else None}
                raise WorkbenchError("CONTENT_WORKBENCH.IDEMPOTENCY_CONFLICT", "candidate identity already has different bytes", 409)
            object_dir.mkdir(parents=True, exist_ok=True); temporary = Path(tempfile.mkdtemp(prefix=".tmp-", dir=object_dir))
            try:
                shutil.copytree(source, temporary / "business", symlinks=False); prior = sorted(object_dir.glob("R[12]/candidate.json")); previous = json.loads(prior[-1].read_text()).get("recordDigest") if prior else None
                record = {"objectId": object_id, "versionId": target, "parentVersionId": parent, "businessDigest": business_digest, "candidateRef": f"candidates/{object_hash}/{target}", "reviewState": "pending_review", "revision": len(prior) + 1, "previousDigest": previous, "recordDigest": record_digest}
                assert_valid(record, "governance", "content_workbench/offline_candidate", label="content workbench offline candidate")
                self._atomic_json(temporary / "candidate.json", record); os.replace(temporary, destination)
            finally:
                if temporary.exists(): shutil.rmtree(temporary)
        item = _extract_object(destination / "business", destination / "business", target, parent=parent); item.update(objectId=object_id, objectRef=record["candidateRef"], businessDigest=business_digest); self._replace_item((object_id, target), item)
        return {**record, "readToken": self._state.token, "stale_read": False, "item": self._clean(item)}
