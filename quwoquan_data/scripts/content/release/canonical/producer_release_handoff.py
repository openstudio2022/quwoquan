"""Create and validate the terminal producer handoff from canonical publish proof.

handoff 以 canonical publish proof（pool record、manifest、content_review、content library 绑定）与
immutable release 事实为凭，不再内嵌 execution receipt 链；累计里程碑可直接复用任何已发布对象。
`producerContractDigest` 记录本次消费的 producer 契约文件 merkle，替代对工作树的 git drift 扫描。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from content.release.canonical.content_pool_handoff import (
    project_content_library_bindings,
    project_content_pool_handoff,
)
from content.release.canonical.object_transaction_contract import (
    CANONICAL_CONTENT_REVIEW_REF,
    ObjectTransactionError,
)
from content.release.canonical.review_rights_binding import (
    required_review_asset_refs,
    validate_content_review_document,
)
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.sealed_release_facts import validate_sealed_release_structure
from core.release_layout import objects_merkle, payload_digest, verify_release_holdings
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy

_SCHEMA = "quwoquan_data.producer_release_handoff"
_FILE_NAME = "producer_release_handoff.json"
_CARRIERS = ("homepage", "article", "image", "video")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
# producer 契约根：Skill 正文、producer schema、执行/来源/canonical 脚本、core 与 prompts。
_PRODUCER_CONTRACT_ROOTS = (
    ".agents/skills/content-production",
    "quwoquan_data/schema/execution",
    "quwoquan_data/schema/source",
    "quwoquan_data/schema/content",
    "quwoquan_data/schema/release",
    "quwoquan_data/scripts/content/execution",
    "quwoquan_data/scripts/content/source",
    "quwoquan_data/scripts/content/release/canonical",
    "quwoquan_data/scripts/core",
    "quwoquan_data/prompts",
    "quwoquan_data/control_plane/_shared/catalogs/content_source_registry.yaml",
    "quwoquan_data/verticals/travel/rights/license_policy.yaml",
)


def producer_contract_digest(repo_root: Path) -> str:
    """当前工作树 producer 契约文件的 merkle（路径 + 字节 sha256，排序后再 sha256）。"""

    rows: list[str] = []
    for root in _PRODUCER_CONTRACT_ROOTS:
        base = repo_root / root
        files = [base] if base.is_file() else sorted(
            path for path in base.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith((".pyc", ".pyo"))
        ) if base.exists() else []
        for path in files:
            rel = path.relative_to(repo_root).as_posix()
            rows.append(f"{rel} sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return "sha256:" + hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


class ProducerReleaseHandoffError(ObjectTransactionError):
    """A typed terminal handoff invariant failed."""


def _error(code: str, detail: str) -> ProducerReleaseHandoffError:
    return ProducerReleaseHandoffError(f"{code}: {detail}")


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _digest(encoded)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_ref(value: object, *, label: str) -> str:
    text = str(value or "")
    ref = PurePosixPath(text)
    if not text or "\x00" in text or ref.is_absolute() or text != ref.as_posix() or any(part in {"", ".", ".."} for part in ref.parts):
        raise _error("DATA.RELEASE.HANDOFF_REF_INVALID", f"{label}={text!r}")
    return text


def _assert_no_symlink(path: Path, *, label: str, regular: bool = True) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise _error("DATA.RELEASE.HANDOFF_REF_SYMLINK", f"{label}={path}")
    except FileNotFoundError as exc:
        raise _error("DATA.RELEASE.HANDOFF_REF_MISSING", f"{label}={path}") from exc
    if regular and not absolute.is_file():
        raise _error("DATA.RELEASE.HANDOFF_REF_INVALID", f"{label} must be regular file")
    if not regular and not absolute.is_dir():
        raise _error("DATA.RELEASE.HANDOFF_REF_INVALID", f"{label} must be directory")
    return absolute


def _read_json_file(path: Path, *, label: str, canonical: bool = False) -> tuple[dict[str, Any], bytes]:
    trusted = _assert_no_symlink(path, label=label)
    raw = trusted.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("DATA.RELEASE.HANDOFF_JSON_INVALID", label) from exc
    if not isinstance(value, dict):
        raise _error("DATA.RELEASE.HANDOFF_JSON_INVALID", f"{label} must be object")
    if canonical and raw != _canonical_bytes(value):
        raise _error("DATA.RELEASE.HANDOFF_NOT_CANONICAL", label)
    return value, raw


def _binding_for_path(path: Path, *, repo_root: Path, output_root: Path, label: str) -> dict[str, str]:
    absolute = _assert_no_symlink(path, label=label)
    for scope, root in (("output", output_root), ("repo", repo_root)):
        trusted_root = _assert_no_symlink(root, label=f"{label} root", regular=False)
        try:
            ref = _safe_ref(absolute.relative_to(trusted_root).as_posix(), label=label)
        except ValueError:
            continue
        return {"scope": scope, "ref": ref, "digest": _digest(absolute.read_bytes())}
    raise _error("DATA.RELEASE.HANDOFF_REF_SCOPE_INVALID", label)


def _counts_from_refs(refs: list[str]) -> dict[str, int]:
    counts = {carrier: 0 for carrier in _CARRIERS}
    for ref in refs:
        normalized = _safe_ref(ref, label="cohort.objectRefs")
        if normalized.startswith("entities/"):
            counts["homepage"] += 1
        elif normalized.startswith("posts/article/"):
            counts["article"] += 1
        elif normalized.startswith("posts/image/"):
            counts["image"] += 1
        elif normalized.startswith("posts/video/"):
            counts["video"] += 1
        else:
            raise _error("DATA.RELEASE.COHORT_REF_INVALID", normalized)
    return {**counts, "total": sum(counts.values())}


def _git(*args: str, repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo_root, check=False, capture_output=True, text=True)


def _validate_producer_baseline_revision(revision: object, *, repo_root: Path) -> str:
    value = str(revision or "")
    if not _COMMIT.fullmatch(value):
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_INVALID", value)
    exists = _git("cat-file", "-e", f"{value}^{{commit}}", repo_root=repo_root)
    if exists.returncode != 0:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_MISSING", value)
    return value


def _carrier_for_ref(object_ref: str) -> tuple[str, str, str]:
    normalized = _safe_ref(object_ref, label="contentPoolObjects.objectRef")
    if normalized.startswith("entities/"):
        return "homepage", "homepage", normalized.removeprefix("entities/")
    if normalized.startswith("posts/"):
        projected_ref = normalized.removeprefix("posts/")
        carrier = projected_ref.split("/", 1)[0]
        if carrier in {"article", "image", "video"}:
            return carrier, "content", projected_ref
    raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", normalized)


def _read_sealed_identity_file(
    sealed_root: Path, ref: object, *, object_ref: str, label: str
) -> dict[str, Any]:
    safe = _safe_ref(ref, label=label)
    if not safe.startswith(f"{object_ref}/"):
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", f"{object_ref} {label}")
    document, _ = _read_json_file(sealed_root / safe, label=f"sealed {label}", canonical=False)
    return document


def _sealed_review_source_assets(
    sealed_object: Path, *, required_asset_refs: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    if not required_asset_refs:
        return {}
    snapshots_root = _assert_no_symlink(
        sealed_object / "rights_snapshots",
        label="canonical rights snapshots",
        regular=False,
    )
    source_assets: dict[str, dict[str, Any]] = {}
    for snapshot_path in sorted(snapshots_root.glob("*.json")):
        snapshot, _ = _read_json_file(
            snapshot_path, label="canonical rights snapshot", canonical=False
        )
        manifest_asset = snapshot.get("manifestAsset")
        if not isinstance(manifest_asset, Mapping):
            raise ObjectTransactionError("canonical rights snapshot lacks manifestAsset")
        refs = [str(manifest_asset.get("sourceAssetRef") or "").strip()]
        raw_refs = manifest_asset.get("sourceAssetRefs")
        if isinstance(raw_refs, list):
            refs.extend(str(ref or "").strip() for ref in raw_refs)
        refs = [ref for ref in refs if ref]
        source_asset = snapshot.get("sourceAsset")
        source_asset_rows = snapshot.get("sourceAssets")
        if isinstance(source_asset, Mapping) and len(refs) == 1:
            pairs = ((refs[0], source_asset),)
        elif (
            isinstance(source_asset_rows, list)
            and all(isinstance(row, Mapping) for row in source_asset_rows)
            and len(refs) == len(source_asset_rows)
        ):
            pairs = tuple(zip(refs, source_asset_rows, strict=True))
        else:
            raise ObjectTransactionError(
                "canonical rights snapshot source binding drift"
            )
        for source_ref, raw_source in pairs:
            source = dict(raw_source)
            existing = source_assets.get(source_ref)
            if existing is not None and existing != source:
                raise ObjectTransactionError(
                    f"canonical source rights facts conflict: {source_ref}"
                )
            source_assets[source_ref] = source
    if set(source_assets) != set(required_asset_refs):
        raise ObjectTransactionError(
            "canonical rights snapshot asset set differs from published assets"
        )
    return source_assets


def _validate_query_against_sealed(
    *,
    row: Mapping[str, Any],
    object_ref: str,
    sealed_root: Path,
    header: Mapping[str, Any],
    release_class: str,
) -> None:
    expected_carrier, expected_type, projected_ref = _carrier_for_ref(object_ref)
    if row.get("objectRef") != object_ref or row.get("carrier") != expected_carrier:
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", object_ref)
    query = row.get("queryDocument")
    if not isinstance(query, Mapping):
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", object_ref)
    try:
        assert_valid(
            query,
            "release",
            "content_pool_handoff_query",
            label=f"contentPoolObjects:{object_ref}",
        )
    except (TypeError, ValueError) as exc:
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", str(exc)) from exc
    if row.get("queryDigest") != canonical_digest(query):
        raise _error("DATA.RELEASE.HANDOFF_POOL_DIGEST_DRIFT", object_ref)
    identity = query.get("identity")
    refs = query.get("refs")
    digests = query.get("digests")
    admission = query.get("admission")
    scope = query.get("scope")
    content_library = query.get("contentLibrary")
    if (
        not isinstance(identity, Mapping)
        or not isinstance(refs, Mapping)
        or not isinstance(digests, Mapping)
        or not isinstance(admission, Mapping)
        or not isinstance(scope, Mapping)
        or not isinstance(content_library, Mapping)
        or identity.get("objectType") != expected_type
        or identity.get("objectRef") != projected_ref
        or identity.get("carrier") != expected_carrier
        or refs.get("canonicalObjectRef") != object_ref
    ):
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", object_ref)

    manifest = _read_sealed_identity_file(
        sealed_root,
        refs.get("manifestRef"),
        object_ref=object_ref,
        label="queryDocument.refs.manifestRef",
    )
    pool_record = _read_sealed_identity_file(
        sealed_root,
        refs.get("poolRecordRef"),
        object_ref=object_ref,
        label="queryDocument.refs.poolRecordRef",
    )
    identity_field = "entityId" if expected_type == "homepage" else "contentId"
    expected_variant = (
        "not_applicable"
        if expected_type == "homepage"
        else str(manifest.get("variantPurpose") or "")
    )
    if (
        manifest.get(identity_field) != identity.get("objectId")
        or manifest.get("version") != identity.get("contentVersion")
        or pool_record.get("objectType") != expected_type
        or pool_record.get("objectId") != identity.get("objectId")
        or pool_record.get("objectRef") != projected_ref
        or pool_record.get("recordSequence") != identity.get("recordSequence")
        or pool_record.get("contentVersion") != identity.get("contentVersion")
        or pool_record.get("canonicalObjectDigest") != digests.get("canonicalObjectDigest")
        or pool_record.get("payloadDigest") != digests.get("payloadDigest")
        or not isinstance(manifest.get("admission"), Mapping)
        or scope.get("usageScope") != pool_record.get("usageScope")
        or scope.get("usageScope") != manifest["admission"].get("usageScope")
        or scope.get("variantPurpose") != expected_variant
    ):
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", object_ref)
    manifest_admission = manifest["admission"]
    for field in (
        "rightsResult",
        "rightsAuthorityRef",
        "rightsAuthorityDigest",
        "evidenceRef",
        "evidenceDigest",
    ):
        if (
            admission.get(field) != pool_record.get(field)
            or admission.get(field) != manifest_admission.get(field)
        ):
            raise _error("DATA.RELEASE.HANDOFF_POOL_RIGHTS_DRIFT", f"{object_ref} {field}")
    if release_class == "commercial" and scope.get("usageScope") != "commercial":
        raise _error("DATA.RELEASE.HANDOFF_COMMERCIAL_SCOPE_INVALID", object_ref)

    binding_ref = content_library.get("bindingRef")
    if binding_ref is None:
        expected_bindings: list[dict[str, object]] = []
    else:
        if binding_ref != f"{object_ref}/asset.refs.json":
            raise _error("DATA.RELEASE.HANDOFF_POOL_BINDING_DRIFT", object_ref)
        binding_document = _read_sealed_identity_file(
            sealed_root,
            binding_ref,
            object_ref=object_ref,
            label="queryDocument.contentLibrary.bindingRef",
        )
        raw_bindings = binding_document.get("assets")
        if not isinstance(raw_bindings, list):
            raise _error("DATA.RELEASE.HANDOFF_POOL_BINDING_DRIFT", object_ref)
        # Sealed release objects intentionally remove private CAS objectKey.
        # Rebind that one delivery-private field from the sealed MediaAsset
        # authority before projecting the producer content-library identity.
        media_manifest, _ = _read_json_file(
            sealed_root.parent / "media_manifest.json",
            label="release MediaAsset authority",
            canonical=False,
        )
        media_by_id = {
            str(asset.get("assetId") or ""): asset
            for asset in media_manifest.get("assets") or []
            if isinstance(asset, Mapping)
        }
        resolved_bindings = []
        for raw in raw_bindings:
            resolved = dict(raw) if isinstance(raw, Mapping) else raw
            if isinstance(resolved, dict) and not resolved.get("objectKey"):
                authority = media_by_id.get(str(resolved.get("assetId") or ""), {})
                resolved["objectKey"] = authority.get("privateObjectKey")
            resolved_bindings.append(resolved)
        try:
            expected_bindings = [
                binding.as_document()
                for binding in project_content_library_bindings(resolved_bindings)
            ]
        except ObjectTransactionError as exc:
            raise _error("DATA.RELEASE.HANDOFF_POOL_BINDING_DRIFT", str(exc)) from exc
    if (
        content_library.get("bindings") != expected_bindings
        or content_library.get("bindingDigest") != canonical_digest(expected_bindings)
    ):
        raise _error("DATA.RELEASE.HANDOFF_POOL_BINDING_DRIFT", object_ref)

    expected_review_ref = f"{object_ref}/{CANONICAL_CONTENT_REVIEW_REF}"
    try:
        content_review = _read_sealed_identity_file(
            sealed_root,
            expected_review_ref,
            object_ref=object_ref,
            label="canonical content review",
        )
        review_path = sealed_root / expected_review_ref
        review_digest = _digest(review_path.read_bytes())
        if (
            admission.get("rightsResult") != "passed"
            or admission.get("evidenceRef") != CANONICAL_CONTENT_REVIEW_REF
            or admission.get("evidenceDigest") != review_digest
            or admission.get("rightsAuthorityRef") != expected_review_ref
            or admission.get("rightsAuthorityDigest") != review_digest
        ):
            raise ObjectTransactionError("canonical content review exact binding drift")
        required_asset_refs = required_review_asset_refs(
            manifest,
            object_kind="posts" if expected_type == "content" else "entities",
        )
        validate_content_review_document(
            content_review,
            execution_id=str(manifest.get("executionId") or ""),
            object_ref=object_ref,
            object_aliases=(projected_ref, str(manifest.get("topicId") or "")),
            required_asset_refs=required_asset_refs,
            source_assets=_sealed_review_source_assets(
                sealed_root / object_ref,
                required_asset_refs=required_asset_refs,
            ),
            require_approved=True,
        )
        if scope.get("usageScope") == "commercial" and (
            not content_review.get("assetRights")
            or any(
                review.get("usageScope") != "commercial"
                for review in content_review.get("assetRights", [])
                if isinstance(review, Mapping)
            )
        ):
            raise ObjectTransactionError("commercial content review usageScope drift")
    except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
        raise _error("DATA.RELEASE.HANDOFF_POOL_RIGHTS_DRIFT", str(exc)) from exc

    if expected_type == "homepage":
        return
    contents = header.get("contents")
    header_rows = [
        content
        for content in contents if isinstance(content, Mapping) and content.get("postRef") == projected_ref
    ] if isinstance(contents, list) else []
    expected = {
        "contentId": identity.get("objectId"),
        "version": identity.get("contentVersion"),
        "postRef": projected_ref,
        "selectionIdentityDigest": digests.get("selectionIdentityDigest"),
        "canonicalObjectDigest": digests.get("canonicalObjectDigest"),
        "contentLibraryBindingDigest": content_library.get("bindingDigest"),
    }
    if header_rows != [expected]:
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", object_ref)


def _project_live_pool_rows(
    *, live_root: Path, sealed_root: Path, object_refs: list[str], header: Mapping[str, Any], release_class: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for object_ref in sorted(object_refs):
        carrier, object_type, projected_ref = _carrier_for_ref(object_ref)
        projected = project_content_pool_handoff(
            publish_root=live_root,
            object_type=object_type,
            object_ref=projected_ref,
        )
        if projected is None:
            raise _error("DATA.RELEASE.HANDOFF_POOL_NOT_PROJECTABLE", object_ref)
        query = projected.as_document()
        row = {
            "objectRef": object_ref,
            "carrier": carrier,
            "queryDocument": query,
            "queryDigest": canonical_digest(query),
        }
        _validate_query_against_sealed(
            row=row,
            object_ref=object_ref,
            sealed_root=sealed_root,
            header=header,
            release_class=release_class,
        )
        rows.append(row)
    return rows


def _validate_embedded_pool_rows(
    *, rows: object, sealed_root: Path, object_refs: list[str], header: Mapping[str, Any], release_class: str
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", "contentPoolObjects")
    expected_refs = sorted(object_refs)
    if [row.get("objectRef") for row in rows if isinstance(row, Mapping)] != expected_refs:
        raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", "contentPoolObjects order/set")
    result: list[dict[str, Any]] = []
    for object_ref, row in zip(expected_refs, rows, strict=True):
        if not isinstance(row, Mapping):
            raise _error("DATA.RELEASE.HANDOFF_POOL_IDENTITY_DRIFT", object_ref)
        _validate_query_against_sealed(
            row=row,
            object_ref=object_ref,
            sealed_root=sealed_root,
            header=header,
            release_class=release_class,
        )
        result.append(dict(row))
    return result



def _validate_release_facts(
    *,
    release_id: str,
    release_root: Path,
    cohort: Mapping[str, Any],
    milestone: str,
    policy_targets: Mapping[str, int] | None = None,
) -> tuple[dict[str, Any], dict[str, int], str, str]:
    release_dir = _assert_no_symlink(release_root / release_id, label="release", regular=False)
    header, header_raw = _read_json_file(release_dir / "payload/release.json", label="release header", canonical=True)
    cohort_release_class = str(cohort.get("releaseClass") or "")
    header_release_class = str(header.get("releaseClass") or "")
    if header_release_class != cohort_release_class:
        raise _error(
            "DATA.RELEASE.HANDOFF_RELEASE_CLASS_DRIFT",
            f"cohort={cohort_release_class!r} header={header_release_class!r}",
        )
    product_lifecycle_state = str(header.get("productLifecycleState") or "")
    if product_lifecycle_state != header_release_class:
        raise _error(
            "DATA.RELEASE.HANDOFF_RELEASE_LIFECYCLE_DRIFT",
            f"releaseClass={header_release_class!r} productLifecycleState={product_lifecycle_state!r}",
        )
    try:
        if policy_targets is None:
            assert_valid(
                header,
                "release",
                "release_header",
                label="producer release handoff header",
            )
        else:
            validate_release_header(header, label="producer release handoff header")
        if objects_merkle(release_dir) != header.get("canonicalMerkle"):
            raise ValueError("canonical Merkle drift")
        holding_issues = verify_release_holdings(release_dir)
        if holding_issues:
            raise ValueError("; ".join(holding_issues))
        desired, _ = _read_json_file(release_dir / "payload/desired_state.json", label="release desired state", canonical=True)
        validate_sealed_release_structure(release_dir=release_dir, desired=desired)
    except (FileNotFoundError, OSError, TypeError, ValueError, ObjectTransactionError) as exc:
        raise _error("DATA.RELEASE.HANDOFF_RELEASE_INTEGRITY_FAILED", str(exc)) from exc
    if header.get("releaseId") != release_id:
        raise _error("DATA.RELEASE.HANDOFF_RELEASE_ID_DRIFT", release_id)
    desired_refs = desired["desiredRefs"]
    release_object_refs = sorted([f"entities/{ref}" for ref in desired_refs["entities"]] + [f"posts/{ref}" for ref in desired_refs["posts"]])
    object_refs = cohort.get("objectRefs")
    if not isinstance(object_refs, list) or object_refs != sorted(object_refs) or release_object_refs != object_refs:
        raise _error("DATA.RELEASE.HANDOFF_COHORT_RELEASE_DRIFT", "release object set differs")
    counts = _counts_from_refs(object_refs)
    expected = cohort.get("expectedCarrierCounts")
    if not isinstance(expected, Mapping) or {key: counts[key] for key in _CARRIERS} != dict(expected):
        raise _error("DATA.RELEASE.COHORT_COUNT_DRIFT", "cohort expectedCarrierCounts differs")
    if cohort.get("milestone") != milestone:
        raise _error("DATA.RELEASE.COHORT_MILESTONE_DRIFT", milestone)
    embedded_targets = header.get("milestoneTargets")
    if (
        not isinstance(embedded_targets, Mapping)
        or {key: counts[key] for key in _CARRIERS} != dict(embedded_targets)
    ):
        raise _error("DATA.RELEASE.COHORT_MILESTONE_COUNT_DRIFT", milestone)
    if policy_targets is not None and dict(embedded_targets) != dict(policy_targets):
        raise _error("DATA.RELEASE.COHORT_MILESTONE_COUNT_DRIFT", milestone)
    if header.get("milestone") != milestone or header.get("counts") != counts:
        raise _error("DATA.RELEASE.HANDOFF_RELEASE_MILESTONE_DRIFT", milestone)
    return header, counts, _digest(header_raw), payload_digest(release_dir)


def _validate_handoff(value: object, *, repo_root: Path, output_root: Path, release_root: Path) -> dict[str, Any]:
    del repo_root, output_root
    try:
        assert_valid(value, "release", "producer_release_handoff", label="producer release handoff")
    except (TypeError, ValueError) as exc:
        raise _error("DATA.RELEASE.HANDOFF_SCHEMA_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _error("DATA.RELEASE.HANDOFF_SCHEMA_INVALID", "document must be object")
    document = dict(value)
    revision = str(document["producerBaselineRevision"])
    if not _COMMIT.fullmatch(revision):
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_INVALID", revision)
    cohort_binding = document["explicitCohort"]
    cohort = cohort_binding.get("document") if isinstance(cohort_binding, Mapping) else None
    if not isinstance(cohort, Mapping):
        raise _error("DATA.RELEASE.COHORT_INVALID", "embedded document missing")
    cohort = dict(cohort)
    try:
        assert_valid(cohort, "release", "release_cohort", label="explicit cohort")
    except ValueError as exc:
        raise _error("DATA.RELEASE.COHORT_INVALID", str(exc)) from exc
    if cohort_binding.get("digest") != _digest(_canonical_bytes(cohort)):
        raise _error("DATA.RELEASE.HANDOFF_DIGEST_DRIFT", "explicit cohort")
    if cohort.get("producerBaselineRevision") != revision:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_DRIFT", revision)
    release_id = str(document["releaseId"])
    milestone = str(document["milestone"])
    header, counts, header_digest, release_digest = _validate_release_facts(
        release_id=release_id, release_root=release_root, cohort=cohort, milestone=milestone
    )
    header_ref = f"data/releases/{release_id}/payload/release.json"
    expected_release = {
        "scope": "output", "ref": f"data/releases/{release_id}", "payloadDigest": release_digest,
        "headerRef": header_ref, "headerDigest": header_digest,
    }
    if document["release"] != expected_release:
        raise _error("DATA.RELEASE.HANDOFF_RELEASE_DIGEST_DRIFT", release_id)
    _validate_embedded_pool_rows(
        rows=document["contentPoolObjects"],
        sealed_root=release_root / release_id / "payload/objects",
        object_refs=list(cohort["objectRefs"]),
        header=header,
        release_class=str(cohort.get("releaseClass") or ""),
    )
    if document["carrierCounts"] != counts:
        raise _error("DATA.RELEASE.HANDOFF_POOL_DIGEST_DRIFT", release_id)
    return document


def validate_producer_release_handoff(
    value: object, *, repo_root: Path, output_root: Path, release_root: Path
) -> dict[str, Any]:
    """只用 sealed release 字节与 handoff 自身重放校验。"""
    return _validate_handoff(
        value, repo_root=repo_root, output_root=output_root, release_root=release_root
    )


def write_producer_release_handoff(*, release_id: str, cohort_file: Path, milestone: str, producer_baseline_revision: str, repo_root: Path, output_root: Path, publish_root: Path, release_root: Path) -> tuple[dict[str, Any], Path, bool]:
    cohort_path = _assert_no_symlink(cohort_file, label="explicit cohort")
    cohort, _ = _read_json_file(cohort_path, label="explicit cohort", canonical=True)
    try:
        assert_valid(cohort, "release", "release_cohort", label="explicit cohort")
    except ValueError as exc:
        raise _error("DATA.RELEASE.COHORT_INVALID", str(exc)) from exc
    revision = _validate_producer_baseline_revision(producer_baseline_revision, repo_root=repo_root)
    if cohort.get("producerBaselineRevision") != revision:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_DRIFT", revision)
    external_cohort_binding = _binding_for_path(cohort_path, repo_root=repo_root, output_root=output_root, label="explicit cohort")
    cohort_binding = {**external_cohort_binding, "document": cohort}
    target = release_root / release_id / _FILE_NAME
    if target.exists():
        try:
            existing_document, _ = _read_json_file(target, label="producer handoff", canonical=True)
            _validate_handoff(existing_document, repo_root=repo_root, output_root=output_root, release_root=release_root)
        except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
            raise _error("DATA.RELEASE.HANDOFF_CREATE_ONCE_CONFLICT", str(target)) from exc
        if (
            existing_document.get("releaseId") != release_id
            or existing_document.get("milestone") != milestone
            or existing_document.get("producerBaselineRevision") != revision
            or existing_document.get("explicitCohort") != cohort_binding
        ):
            raise _error("DATA.RELEASE.HANDOFF_CREATE_ONCE_CONFLICT", str(target))
        return existing_document, target, True

    policy_targets = load_content_distribution_policy().milestone_targets().get(milestone)
    if policy_targets is None:
        raise _error("DATA.RELEASE.COHORT_MILESTONE_INVALID", milestone)
    header, counts, header_digest, release_digest = _validate_release_facts(
        release_id=release_id, release_root=release_root, cohort=cohort,
        milestone=milestone, policy_targets=policy_targets,
    )
    header_ref = f"data/releases/{release_id}/payload/release.json"
    pool_rows = _project_live_pool_rows(
        live_root=publish_root,
        sealed_root=release_root / release_id / "payload/objects",
        object_refs=list(cohort["objectRefs"]),
        header=header,
        release_class=str(cohort.get("releaseClass") or ""),
    )
    document = {
        "schema": _SCHEMA,
        "handoffId": release_id,
        "releaseId": release_id,
        "milestone": milestone,
        "carrierCounts": counts,
        "release": {
            "scope": "output", "ref": f"data/releases/{release_id}", "payloadDigest": release_digest,
            "headerRef": header_ref, "headerDigest": header_digest,
        },
        "explicitCohort": cohort_binding,
        "contentPoolObjects": pool_rows,
        "producerBaselineRevision": revision,
        "producerContractDigest": producer_contract_digest(repo_root),
    }
    assert_valid(document, "release", "producer_release_handoff", label="producer release handoff")
    encoded = _canonical_bytes(document)
    parent = _assert_no_symlink(target.parent, label="release", regular=False)
    temporary = parent / f".{_FILE_NAME}.{secrets.token_hex(12)}.tmp"
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            if _assert_no_symlink(target, label="producer handoff").read_bytes() != encoded:
                raise _error("DATA.RELEASE.HANDOFF_CREATE_ONCE_CONFLICT", str(target)) from None
            return document, target, True
        return document, target, False
    finally:
        temporary.unlink(missing_ok=True)


def read_producer_release_handoff(
    path: Path, *, repo_root: Path, output_root: Path, release_root: Path
) -> dict[str, Any]:
    document, raw = _read_json_file(path, label="producer release handoff", canonical=True)
    if raw != _canonical_bytes(document):
        raise _error("DATA.RELEASE.HANDOFF_NOT_CANONICAL", str(path))
    return validate_producer_release_handoff(document, repo_root=repo_root, output_root=output_root, release_root=release_root)


__all__ = ["ProducerReleaseHandoffError", "producer_contract_digest", "read_producer_release_handoff", "validate_producer_release_handoff", "write_producer_release_handoff"]
