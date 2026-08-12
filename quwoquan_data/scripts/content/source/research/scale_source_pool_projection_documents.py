"""Physical evidence loading for media scale source-pool projection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, NoReturn

from core.schema import assert_valid


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_path(
    root: Path,
    ref: object,
    *,
    label: str,
    fail: Callable[[str], NoReturn],
) -> tuple[Path, str]:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        fail(f"{label} must be a safe relative reference")
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            fail(f"{label} must not traverse a symlink")
    if not current.is_file():
        fail(f"{label} is missing: {relative.as_posix()}")
    return current, relative.as_posix()


def _document_digest(
    document: Mapping[str, Any],
    *,
    kind: str,
    fail: Callable[[str], NoReturn],
) -> str:
    if kind == "image_catalog":
        if document.get("schema") == (
            "quwoquan_data.professional_image_public_candidate_catalog"
        ):
            fields = (
                "catalogRevision",
                "discoveryPlanId",
                "discoveryPlanDigest",
                "observedAt",
                "sourceResponses",
                "providerCounts",
                "candidateCount",
                "rejectedAssetCount",
                "candidates",
                "rejections",
            )
        elif document.get("schema") == (
            "quwoquan_data.professional_image_governed_candidate_catalog"
        ):
            fields = (
                "catalogRevision",
                "discoveryPlanId",
                "discoveryPlanDigest",
                "createdAt",
                "providerCounts",
                "candidateCount",
                "candidates",
            )
        else:
            fail("image catalog schema is not governed")
        return _digest({field: document[field] for field in fields})
    if kind == "video_catalog":
        return _digest(
            {
                key: value
                for key, value in document.items()
                if key not in {"catalogId", "catalogDigest"}
            }
        )
    return _digest(
        {key: value for key, value in document.items() if key != "receiptDigest"}
    )


def _validate_governed_catalog_evidence(
    document: Mapping[str, Any],
    *,
    root: Path,
    fail: Callable[[str], NoReturn],
) -> None:
    if document.get("schema") != (
        "quwoquan_data.professional_image_governed_candidate_catalog"
    ):
        return
    for candidate in document["candidates"]:
        binding = candidate["pathEvidence"]
        path, ref = _safe_path(
            root,
            binding["ref"],
            label="imageCandidateEvidenceRef",
            fail=fail,
        )
        if _file_digest(path) != binding["fileSha256"]:
            fail(f"image candidate evidence file drift: {ref}")
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            fail(f"image candidate evidence is not readable JSON: {ref}: {exc}")
        if not isinstance(evidence, dict) or _digest(evidence) != binding["digest"]:
            fail(f"image candidate evidence digest drift: {ref}")


def load_documents(
    refs: Iterable[str],
    *,
    root: Path,
    kind: str,
    schema_name: str | Mapping[str, str],
    fail: Callable[[str], NoReturn],
) -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = []
    seen: set[str] = set()
    digest_field = (
        "catalogDigest"
        if kind in {"image_catalog", "video_catalog"}
        else "receiptDigest"
    )
    for raw_ref in sorted(str(ref).strip() for ref in refs):
        path, ref = _safe_path(root, raw_ref, label=f"{kind}Ref", fail=fail)
        if ref in seen:
            fail(f"duplicate {kind} reference: {ref}")
        seen.add(ref)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            fail(f"{kind} is not readable JSON: {ref}: {exc}")
        if not isinstance(document, dict):
            fail(f"{kind} must be an object: {ref}")
        selected_schema = schema_name
        if isinstance(schema_name, Mapping):
            selected_schema = schema_name.get(str(document.get("schema") or ""), "")
            if not selected_schema:
                fail(f"{kind} schema is not an accepted catalog type: {ref}")
        try:
            assert_valid(document, "source", selected_schema, label=kind)
        except (FileNotFoundError, TypeError, ValueError) as exc:
            fail(f"{kind} schema failure: {ref}: {exc}")
        semantic = _document_digest(document, kind=kind, fail=fail)
        if document.get(digest_field) != semantic:
            fail(f"{kind} document digest drift: {ref}")
        if kind == "image_catalog":
            _validate_governed_catalog_evidence(
                document,
                root=root,
                fail=fail,
            )
        loaded.append(
            {
                "kind": kind,
                "ref": ref,
                "documentDigest": semantic,
                "fileSha256": _file_digest(path),
                "document": document,
            }
        )
    return loaded


__all__ = ["load_documents"]
