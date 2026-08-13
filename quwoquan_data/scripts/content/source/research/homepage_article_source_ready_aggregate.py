"""Aggregate current-identity source-ready batches without copying media bytes."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.source.research.homepage_article_source_ready_batch import (
    SOURCE_INVALID_EVIDENCE,
    HomepageArticleSourceReadyBatchError,
    _digest,
    _file_sha256,
    _safe_directory,
    _safe_file,
    load_homepage_article_source_ready_batch,
)
from content.source.research.homepage_article_source_ready_evidence import (
    write_create_once_json,
)
from content.source.research.homepage_article_seed_selection import (
    load_homepage_article_seed_selection,
)

AGGREGATE_SCHEMA = "quwoquan_data.homepage_article_source_ready_aggregate"
_IDENTITY_FIELDS = ("sourceRevision", "sourceDigest", "entityCatalogDigest")


def _invalid(issue: str) -> HomepageArticleSourceReadyBatchError:
    return HomepageArticleSourceReadyBatchError(SOURCE_INVALID_EVIDENCE, [issue])


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(str(value.get(field) or "") for field in _IDENTITY_FIELDS)


def _relative_file(output_root: Path, path: Path, *, label: str) -> tuple[Path, str]:
    root = _safe_directory(output_root, ".", label="outputRoot")
    selected = path.expanduser().absolute()
    try:
        relative = selected.relative_to(root)
    except ValueError as exc:
        raise _invalid(f"{label} must be inside outputRoot") from exc
    safe = _safe_file(root, relative.as_posix(), label=label)
    return safe, relative.as_posix()


def _member_evidence_root(path: Path, *, output_root: Path) -> tuple[Path, str]:
    if path.parent.name != "batches":
        raise _invalid("member batch must use the canonical batches directory")
    member_root = path.parent.parent
    try:
        relative = member_root.relative_to(output_root)
    except ValueError as exc:
        raise _invalid("member evidence root must be inside outputRoot") from exc
    ref = relative.as_posix()
    return _safe_directory(output_root, ref, label="member.evidenceRootRef"), ref


def _rebase_binding(
    binding: Mapping[str, Any],
    *,
    member_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    candidate_root = _safe_directory(
        member_root,
        binding.get("evidenceRootRef"),
        label="member.candidate.evidenceRootRef",
    )
    try:
        root_ref = candidate_root.relative_to(output_root).as_posix()
    except ValueError as exc:
        raise _invalid("candidate evidence root must be inside outputRoot") from exc
    return {**dict(binding), "evidenceRootRef": root_ref}


def merge_homepage_article_source_ready_batches(
    *,
    batch_manifests: Sequence[Path],
    output_root: Path,
    source_set_id: str,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    created_at: str,
) -> dict[str, Any]:
    """Create one aggregate projection and a normal batch manifest over members."""

    if len(batch_manifests) < 2:
        raise _invalid("at least two source-ready member batches are required")
    root = output_root.expanduser().absolute()
    _safe_directory(root, ".", label="outputRoot")
    expected_identity = (source_revision, source_digest, entity_catalog_digest)
    members: list[dict[str, Any]] = []
    candidate_bindings: list[dict[str, Any]] = []
    source_set_ids: set[str] = set()
    member_digests: set[str] = set()
    counts = {"homepage": 0, "article": 0}
    aggregate_seeds: list[dict[str, Any]] = []
    aggregate_seed_ids: set[str] = set()
    for index, manifest in enumerate(batch_manifests):
        path, ref = _relative_file(root, manifest, label=f"memberBatches[{index}]")
        member_root, member_root_ref = _member_evidence_root(path, output_root=root)
        loaded = load_homepage_article_source_ready_batch(
            path, evidence_root=member_root
        )
        batch = loaded["batch"]
        assert isinstance(batch, dict)
        if batch.get("targetScale") != target_scale:
            raise _invalid(f"memberBatches[{index}] targetScale drift")
        if _identity(batch) != expected_identity:
            raise _invalid(f"memberBatches[{index}] source identity drift")
        member_id = str(batch["sourceSetId"])
        member_digest = str(batch["sourceSetDigest"])
        if member_id in source_set_ids or member_digest in member_digests:
            raise _invalid("member batches must be unique")
        source_set_ids.add(member_id)
        member_digests.add(member_digest)
        member_counts = dict(batch["counts"])
        for carrier in counts:
            counts[carrier] += int(member_counts[carrier])
        members.append(
            {
                "sourceSetId": member_id,
                "ref": ref,
                "evidenceRootRef": member_root_ref,
                "digest": member_digest,
                "fileSha256": _file_sha256(path),
                "counts": member_counts,
            }
        )
        candidate_bindings.extend(
            _rebase_binding(row, member_root=member_root, output_root=root)
            for row in batch["candidateCapsules"]
            if isinstance(row, Mapping)
        )
        seed_path = _safe_file(
            member_root,
            batch["seedSelection"]["ref"],
            label=f"memberBatches[{index}].seedSelection",
        )
        seed_selection = load_homepage_article_seed_selection(seed_path)
        accepted_seed_ids: set[str] = set()
        for binding_index, raw_binding in enumerate(batch["candidateCapsules"]):
            assert isinstance(raw_binding, Mapping)
            candidate_root = _safe_directory(
                member_root,
                raw_binding.get("evidenceRootRef"),
                label=(
                    f"memberBatches[{index}].candidateCapsules"
                    f"[{binding_index}].evidenceRootRef"
                ),
            )
            capsule_path = _safe_file(
                candidate_root,
                raw_binding.get("ref"),
                label=(
                    f"memberBatches[{index}].candidateCapsules"
                    f"[{binding_index}]"
                ),
            )
            capsule = read_json(capsule_path)
            if not isinstance(capsule, Mapping):
                raise _invalid(
                    f"memberBatches[{index}] candidate capsule must be an object"
                )
            provenance = capsule.get("provenance")
            seed_id = (
                str(provenance.get("seedId") or "")
                if isinstance(provenance, Mapping)
                else ""
            )
            if not seed_id or seed_id in accepted_seed_ids:
                raise _invalid(
                    f"memberBatches[{index}] candidate seed binding is invalid"
                )
            accepted_seed_ids.add(seed_id)
        selected_seeds = [
            dict(row)
            for row in seed_selection["seeds"]
            if isinstance(row, Mapping)
            and str(row.get("seedId") or "") in accepted_seed_ids
        ]
        if len(selected_seeds) != len(accepted_seed_ids):
            raise _invalid(
                f"memberBatches[{index}] accepted seed selection is incomplete"
            )
        for seed in selected_seeds:
            seed_id = str(seed["seedId"])
            if seed_id in aggregate_seed_ids:
                raise _invalid("member batches overlap on accepted seed identity")
            aggregate_seed_ids.add(seed_id)
            aggregate_seeds.append(seed)
    members.sort(key=lambda row: (str(row["digest"]), str(row["ref"])))
    candidate_bindings.sort(
        key=lambda row: (str(row["carrier"]), str(row["candidateId"]), str(row["digest"]))
    )
    identity = dict(zip(_IDENTITY_FIELDS, expected_identity, strict=True))
    stable_projection: dict[str, Any] = {
        "schema": AGGREGATE_SCHEMA,
        "sourceSetId": source_set_id,
        "targetScale": target_scale,
        **identity,
        "createdAt": created_at,
        "memberBatches": members,
        "counts": counts,
    }
    projection = {
        **stable_projection,
        "projectionDigest": _digest(stable_projection),
    }
    try:
        assert_valid(
            projection,
            "source",
            "homepage_article_source_ready_aggregate",
            label="homepage/article source-ready aggregate",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _invalid(str(exc)) from exc
    aggregate_root = (
        root / "homepage-article-source-ready" / target_scale.lower() / source_set_id
    )
    projection_path = aggregate_root / "aggregates" / (
        projection["projectionDigest"].removeprefix("sha256:") + ".json"
    )
    write_create_once_json(projection_path, projection)
    projection_ref = projection_path.relative_to(root).as_posix()
    aggregate_seeds.sort(
        key=lambda row: (
            str(row["coverageKey"]["carrier"]),
            str(row["coverageKey"]["entityRef"]),
            str(row["coverageKey"]["sourceUrl"]),
        )
    )
    stable_seed_selection = {
        "schema": "quwoquan_data.homepage_article_seed_selection",
        "seedSetId": source_set_id,
        "counts": counts,
        "seeds": aggregate_seeds,
    }
    seed_selection = {
        **stable_seed_selection,
        "selectionDigest": _digest(stable_seed_selection),
    }
    seed_path = aggregate_root / "seed-selections" / (
        seed_selection["selectionDigest"].removeprefix("sha256:") + ".json"
    )
    write_create_once_json(seed_path, seed_selection)
    seed_ref = seed_path.relative_to(root).as_posix()
    stable_batch: dict[str, Any] = {
        "schema": "quwoquan_data.homepage_article_source_ready_batch",
        "sourceSetId": source_set_id,
        "targetScale": target_scale,
        **identity,
        "createdAt": created_at,
        "coverageProjection": {
            "ref": projection_ref,
            "digest": projection["projectionDigest"],
            "fileSha256": _file_sha256(projection_path),
        },
        "seedSelection": {
            "ref": seed_ref,
            "digest": seed_selection["selectionDigest"],
            "fileSha256": _file_sha256(seed_path),
        },
        "candidateCapsules": candidate_bindings,
        "counts": counts,
    }
    batch = {**stable_batch, "sourceSetDigest": _digest(stable_batch)}
    try:
        assert_valid(
            batch,
            "source",
            "homepage_article_source_ready_batch",
            label="merged homepage/article source-ready batch",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _invalid(str(exc)) from exc
    batch_path = aggregate_root / "batches" / (
        batch["sourceSetDigest"].removeprefix("sha256:") + ".json"
    )
    write_create_once_json(batch_path, batch)
    loaded = load_homepage_article_source_ready_batch(batch_path, evidence_root=root)
    if loaded["batch"].get("counts") != counts:
        raise _invalid("merged batch counts drift after create-once write")
    return {
        "schema": "quwoquan_data.homepage_article_source_ready_aggregate_result",
        "evidenceRoot": str(root),
        "sourceReadyManifest": str(batch_path),
        "sourceReadySetRef": batch_path.relative_to(root).as_posix(),
        "sourceSetDigest": batch["sourceSetDigest"],
        "sourceReadySetFileSha256": _file_sha256(batch_path),
        "aggregateProjectionRef": projection_ref,
        "aggregateProjectionDigest": projection["projectionDigest"],
        "memberCount": len(members),
        "counts": counts,
    }


__all__ = ["AGGREGATE_SCHEMA", "merge_homepage_article_source_ready_batches"]
