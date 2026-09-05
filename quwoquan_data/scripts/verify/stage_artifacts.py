"""对象阶段截止闭包与 publish 后 final artifact 闭包门。"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from core.content_library import library_cas_path, library_root_for_output
from core.io import read_json
from core.paths import PUBLISH_ROOT, RELEASE_ROOT, execution_root
from core.schema import assert_valid
from core.stage_artifact_contract import (
    CANONICAL_FORBIDDEN_PROCESS_ARTIFACT_NAMES,
    STAGES,
    required_final_artifacts,
    required_stage_artifacts,
)


@dataclass(frozen=True)
class ArtifactSchema:
    command: str
    name: str
    requires_frozen_binding: bool = False


_SCHEMA_FILES = {
    "2.quality/quality_analysis.json": ArtifactSchema("content", "quality_analysis", True),
    "3.compose/entity_page_input.json": ArtifactSchema("content", "entity_page_input", True),
    "3.compose/writing_pack.json": ArtifactSchema("content", "writing_pack", True),
    "4.draft/image_work.json": ArtifactSchema("content", "image_work"),
    "4.draft/video_script.json": ArtifactSchema("content", "video_script"),
    "5.review/content_review.json": ArtifactSchema("content", "content_review"),
}

_IDENTITY_FIELDS = ("executionId",)
_COMPOSE_HOMEPAGE_REL = "3.compose/entity_page_input.json"
_COMPOSE_PACK_REL = "3.compose/writing_pack.json"
_VIDEO_SCRIPT_REL = "4.draft/video_script.json"


def _validate_json(
    path: Path,
    schema: ArtifactSchema | tuple[str, str],
    issues: list[str],
) -> dict[str, Any]:
    try:
        payload = read_json(path)
        if isinstance(schema, ArtifactSchema):
            assert_valid(payload, schema.command, schema.name, label=path.as_posix())
        else:
            assert_valid(payload, *schema, label=path.as_posix())
        return payload
    except Exception as exc:  # noqa: BLE001
        issues.append(f"{path}: schema invalid ({exc})")
        return {}


def _boundary_issues(root: Path, *, root_kind: str) -> list[str]:
    if not root.is_dir():
        return []
    issues: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir() and path.name in STAGES:
            issues.append(f"{root_kind}: process stage directory forbidden: {path}")
        if (
            path.is_file()
            and path.name in CANONICAL_FORBIDDEN_PROCESS_ARTIFACT_NAMES
        ):
            issues.append(f"{root_kind}: process artifact forbidden: {path}")
        lower_parts = {part.lower() for part in path.parts}
        if path.is_file() and (
            "calibration" in lower_parts
            or "benchmark" in lower_parts
            or "raw_logs" in lower_parts
        ):
            issues.append(f"{root_kind}: run-only evidence forbidden: {path}")
    return issues


def _object_lane(object_root: Path) -> str:
    if (object_root / _COMPOSE_HOMEPAGE_REL).is_file():
        return "homepage"
    writing_pack = read_json(object_root / _COMPOSE_PACK_REL)
    carrier = str(writing_pack.get("carrier") or "").lower()
    if carrier == "image":
        return "image"
    if carrier == "video":
        return "video"
    return "article"


def object_stage_contract_issues(object_root: Path, lane: str) -> list[str]:
    """验证四类 lane 的同一五阶段契约。"""
    issues: list[str] = []
    for stage, rels in required_stage_artifacts(lane).items():
        for rel in rels:
            if not (object_root / stage / rel).is_file():
                issues.append(f"{lane}.{stage}.{rel} 缺失")
    # Accepted source units are execution-owned at ``sources/<sourceUnitId>``.
    # Objects retain only source_refs.json, which the execution-level verifier
    # resolves against that canonical root. An object-local source_units tree is
    # retired and must not become a second source-layout contract.
    for rel in required_final_artifacts(lane):
        if not (object_root / rel).is_file():
            issues.append(f"{lane}.final.{rel} 缺失")
    return issues


def _object_roots(root: Path, through: str | None) -> list[Path]:
    """发现 target_set 声明对象及已有阶段锚点，禁止缺对象假绿。"""
    declared: set[Path] = set()
    target_set_path = root / "0.plan/target_set.json"
    if target_set_path.is_file():
        target_set = read_json(target_set_path)
        for raw_ref in target_set.get("targetRefs") or []:
            ref = str(raw_ref).strip().strip("/")
            if ref.startswith(("entities/", "posts/")) and ".." not in Path(ref).parts:
                declared.add(root / ref)
    anchors = {
        *root.glob(f"**/{_COMPOSE_HOMEPAGE_REL}"),
        *root.glob(f"**/{_COMPOSE_PACK_REL}"),
    }
    if through == "4.draft":
        anchors |= {*root.glob(f"**/{_VIDEO_SCRIPT_REL}")}
    if through in ("1.download", "2.quality"):
        anchors |= {
            *root.glob("**/1.download/source_refs.json"),
            *root.glob("**/2.quality/quality_analysis.json"),
        }
    return sorted(declared | {path.parent.parent for path in anchors})


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _direct_ref(binding: Any, *, expected_ref: str, expected_digest: str) -> bool:
    return (
        isinstance(binding, dict)
        and binding.get("ref") == expected_ref
        and binding.get("digest") == expected_digest
    )


def _safe_execution_path(root: Path, ref: object) -> Path | None:
    value = str(ref or "").strip()
    candidate = root / value
    try:
        candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def _selected_source_ids(quality: Mapping[str, Any]) -> set[str]:
    selected: set[str] = set()
    for row in quality.get("sourceAdmissions") or []:
        if not isinstance(row, Mapping) or row.get("decision") != "selected":
            continue
        source_ref = str(row.get("sourceRef") or "")
        parts = Path(source_ref).parts
        if len(parts) >= 3 and parts[0] == "sources":
            selected.add(parts[1])
    return selected


def _compose_source_ids(compose: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    for value in compose.get("selectedSourceRefs") or []:
        parts = Path(str(value or "")).parts
        if len(parts) >= 3 and parts[0] == "sources":
            refs.add(parts[1])
    return refs


def _quality_anchor_issues(
    root: Path,
    source_refs: Mapping[str, Any],
    quality: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = []
    known = {
        str(row.get("sourceRef") or ""): str(row.get("sourceUnitId") or "")
        for row in source_refs.get("sources") or []
        if isinstance(row, Mapping)
    }
    selected_rows = [
        row
        for row in quality.get("sourceAdmissions") or []
        if isinstance(row, Mapping) and row.get("decision") == "selected"
    ]
    for row in selected_rows:
        source_ref = str(row.get("sourceRef") or "")
        if source_ref not in known:
            issues.append(f"quality selected source is outside source_refs: {source_ref or '<empty>'}")
        source_path = _safe_execution_path(root, source_ref)
        if source_path is None or not source_path.is_file():
            issues.append(f"quality selected source is unresolved: {source_ref or '<empty>'}")
            continue
        if row.get("evidenceHash") != _digest(source_path):
            issues.append(f"quality evidence anchor digest drift: {source_ref}")
    declared_hashes = sorted(str(value) for value in quality.get("evidenceHashes") or [])
    selected_hashes = sorted(str(row.get("evidenceHash") or "") for row in selected_rows)
    if declared_hashes != selected_hashes:
        issues.append("quality evidenceHashes differ from selected source anchors")
    return issues


def _download_source_issues(root: Path, row: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    meta_path = _safe_execution_path(root, row.get("metaRef"))
    source_path = _safe_execution_path(root, row.get("sourceRef"))
    plan_path = _safe_execution_path(root, row.get("sourcePlanRef"))
    if any(path is None or path.is_symlink() or not path.is_file() for path in (meta_path, source_path, plan_path)):
        return ["unresolved source/meta/plan ref"]
    assert meta_path is not None and source_path is not None and plan_path is not None
    meta = read_json(meta_path)
    schema_name = "atomic_source_unit_meta" if meta.get("schema") == "quwoquan_data.atomic_source_unit" else "source_unit_meta"
    try:
        assert_valid(meta, "source", schema_name, label=meta_path.as_posix())
    except Exception as exc:  # noqa: BLE001
        return [f"source meta invalid ({exc})"]
    if row.get("sourceUnitId") != meta.get("sourceUnitId"):
        issues.append("source unit identity drift")
    for field in ("sourcePlanRef", "sourcePlanDigest", "chosenCandidateDigest"):
        if row.get(field) != meta.get(field):
            issues.append(f"source refs/meta {field} drift")
    if _digest(plan_path) != meta.get("sourcePlanDigest"):
        issues.append("source plan digest drift")
    try:
        plan = read_json(plan_path)
        assert_valid(plan, "source", "source_plan", label=plan_path.as_posix())
    except Exception as exc:  # noqa: BLE001
        issues.append(f"source plan invalid ({exc})")
        plan = {}
    if plan.get("executionId") != root.name or plan.get("targetRef") != meta.get("targetRef"):
        issues.append("source plan identity drift")
    candidates = plan.get("candidates") if isinstance(plan, Mapping) else []
    expected_candidates = []
    for candidate in candidates or []:
        if not isinstance(candidate, Mapping) or candidate.get("sourceId") != meta.get("sourceId"):
            continue
        candidate_input = {
            "schema": "quwoquan_data.source_candidate",
            "sourcePlanRef": meta.get("sourcePlanRef"),
            "sourcePlanDigest": meta.get("sourcePlanDigest"),
            **dict(candidate),
        }
        expected_candidates.append(candidate_input)
    if len(expected_candidates) != 1:
        issues.append("chosen source candidate is not unique in source plan")
    else:
        candidate_variants = [expected_candidates[0]]
        if meta.get("fetchedAt"):
            candidate_variants.append(
                {**expected_candidates[0], "fetchedAt": meta["fetchedAt"]}
            )
        expected_digests = {
            "sha256:"
            + hashlib.sha256(
                (
                    json.dumps(
                        candidate,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            for candidate in candidate_variants
        }
        if meta.get("chosenCandidateDigest") not in expected_digests:
            issues.append("chosen candidate exact binding drift")
    if meta_path.parent != source_path.parent or not source_path.read_bytes():
        issues.append("source body binding invalid")
    if _digest(source_path) != meta.get("sourceMarkdownSha256"):
        issues.append("source markdown digest drift")
    snapshot_name = "snapshot.bin" if isinstance(meta.get("acquisition"), Mapping) else "snapshot.raw"
    snapshot_path = meta_path.parent / snapshot_name
    if snapshot_path.is_symlink() or not snapshot_path.is_file() or _digest(snapshot_path) != meta.get("rawSha256"):
        issues.append("source snapshot exact bytes drift")
    assets_path = meta_path.parent / "assets/index.json"
    if assets_path.is_symlink() or not assets_path.is_file():
        issues.append("source unit assets/index.json missing")
        return issues
    assets = read_json(assets_path).get("assets") or []
    acquisition = meta.get("acquisition")
    if isinstance(acquisition, Mapping):
        required = {
            str(acquisition.get("assetRef") or ""): str(acquisition.get("contentSha256") or ""),
        }
        if acquisition.get("posterAssetRef"):
            required[str(acquisition["posterAssetRef"])] = str(acquisition.get("posterContentSha256") or "")
        output_root = root.parents[2]
        library_root = library_root_for_output(output_root)
        for asset_ref, digest in required.items():
            asset_path = meta_path.parent / asset_ref
            matching = [
                asset
                for asset in assets
                if isinstance(asset, Mapping) and asset.get("fileName") == asset_path.name
            ]
            if len(matching) != 1 or asset_path.is_symlink() or not asset_path.is_file():
                issues.append(f"acquisition asset binding missing: {asset_ref}")
                continue
            actual = _digest(asset_path)
            if actual != digest or matching[0].get("contentSha256") != digest:
                issues.append(f"acquisition asset digest drift: {asset_ref}")
            cas = library_cas_path("media", digest, library_root=library_root)
            if not cas.is_file() or _digest(cas) != digest:
                issues.append(f"acquisition CAS holding drift: {asset_ref}")
    return issues


def _draft_binding_issues(root: Path, obj: Path, *, lane: str, object_ref: str) -> list[str]:
    open_path = root / "_shared/stage-open/006-4.draft.json"
    if not open_path.is_file():
        return ["缺少 sequence-006 OPEN，无法证明 draft direct compose binding"]
    opened = read_json(open_path)
    compose_ref = _COMPOSE_HOMEPAGE_REL if lane == "homepage" else _COMPOSE_PACK_REL
    compose_path = obj / compose_ref
    input_refs = opened.get("inputRefs") if isinstance(opened, dict) else []
    if not any(
        row.get("scope") == "execution"
        and row.get("ref") == f"{object_ref}/{compose_ref}"
        and row.get("digest") == _digest(compose_path)
        for row in input_refs or [] if isinstance(row, dict)
    ):
        return ["sequence-006 OPEN 未 exact 绑定 direct compose"]
    return []


def _source_unit_refs(obj: Path) -> tuple[str, ...]:
    source_refs_path = obj / "1.download/source_refs.json"
    if not source_refs_path.is_file():
        return ()
    source_refs = read_json(source_refs_path)
    rows = source_refs.get("sources") if isinstance(source_refs, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("source_refs sources must be an array")
    refs: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("source_refs source row must be an object")
        meta_ref = str(row.get("metaRef") or "").strip().strip("/")
        parts = Path(meta_ref).parts
        if (
            len(parts) != 3
            or parts[0] != "sources"
            or parts[1] in {"", ".", "..", "plans"}
            or parts[2] != "meta.json"
        ):
            raise ValueError(f"source_refs metaRef invalid: {meta_ref or '<empty>'}")
        refs.append(Path(*parts[:-1]).as_posix())
    if len(refs) != len(set(refs)):
        raise ValueError("source_refs source units are duplicated")
    return tuple(refs)


def _assert_selected_source_asset_refs(
    refs: list[str],
    *,
    root: Path,
    obj: Path,
) -> tuple[str, ...]:
    normalized = [str(ref or "").strip().strip("/") for ref in refs]
    if any(not ref for ref in normalized):
        raise ValueError("selected asset refs must be non-empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError("selected asset refs must be unique")
    source_units = _source_unit_refs(obj)
    if not source_units and normalized:
        raise ValueError("selected assets lack object source_refs binding")
    for ref in normalized:
        path = Path(ref)
        if (
            not ref.startswith("sources/")
            or path.is_absolute()
            or ".." in path.parts
            or not any(ref.startswith(f"{unit_ref}/assets/") for unit_ref in source_units)
        ):
            raise ValueError(f"selected asset ref is outside object source units: {ref}")
        asset_path = root / path
        if asset_path.is_symlink() or not asset_path.is_file():
            raise ValueError(f"selected source asset is missing: {ref}")
    return tuple(normalized)


def _compose_asset_refs(raw_assets: object) -> list[str]:
    if raw_assets is None:
        return []
    if not isinstance(raw_assets, list):
        raise ValueError("compose assets must be an array")
    refs: list[str] = []
    for raw in raw_assets:
        if not isinstance(raw, Mapping):
            raise ValueError("compose asset row must be an object")
        direct = str(raw.get("sourceAssetRef") or raw.get("assetRef") or "").strip()
        if direct:
            refs.append(direct)
        many = raw.get("sourceAssetRefs")
        if many is not None:
            if not isinstance(many, list):
                raise ValueError("compose sourceAssetRefs must be an array")
            refs.extend(str(value or "").strip() for value in many)
    return refs


def _video_poster_ref(
    video_ref: str,
    explicit_poster_ref: str,
    *,
    root: Path,
    source_assets: Mapping[str, Mapping[str, Any]],
) -> str:
    video = source_assets.get(video_ref)
    if not isinstance(video, Mapping):
        raise ValueError(f"selected source video is missing: {video_ref}")
    if str(video.get("assetRole") or "").strip() != "video":
        raise ValueError(f"selected source video has non-video role: {video_ref}")
    parent = Path(video_ref).parent
    meta_path = root / parent.parent / "meta.json"
    meta = read_json(meta_path) if meta_path.is_file() else {}
    acquisition = meta.get("acquisition") if isinstance(meta, Mapping) else None
    recorded_relative = (
        str(acquisition.get("posterAssetRef") or "").strip()
        if isinstance(acquisition, Mapping)
        else ""
    )
    recorded_ref = (
        (parent.parent / recorded_relative).as_posix()
        if recorded_relative
        else ""
    )
    poster_ref = explicit_poster_ref or recorded_ref
    if not poster_ref:
        raise ValueError(
            f"selected source video lacks an exact poster binding: {video_ref}"
        )
    if recorded_ref and poster_ref != recorded_ref:
        raise ValueError(f"selected source video poster binding drift: {video_ref}")
    poster = source_assets.get(poster_ref)
    if not isinstance(poster, Mapping):
        raise ValueError(f"selected source poster is missing: {poster_ref}")
    if (
        Path(poster_ref).parent != parent
        or str(poster.get("assetRole") or "").strip() != "poster"
    ):
        raise ValueError(f"selected source poster is not paired with video: {poster_ref}")
    video_source_id = str(video.get("sourceAssetId") or "").strip()
    derived_from = str(poster.get("derivedFromSourceAssetId") or "").strip()
    if derived_from and derived_from != video_source_id:
        raise ValueError(f"selected source poster derivation drift: {poster_ref}")
    return poster_ref


def _review_asset_refs(
    *,
    root: Path,
    obj: Path,
    lane: str,
    draft: Mapping[str, Any],
    compose: Mapping[str, Any],
    source_assets: Mapping[str, Mapping[str, Any]],
) -> tuple[str, ...]:
    if lane == "image":
        raw_refs = draft.get("assetRefs")
        if not isinstance(raw_refs, list) or not raw_refs:
            raise ValueError("image_work.assetRefs must select at least one asset")
        refs = [str(value or "").strip() for value in raw_refs]
    elif lane == "video":
        source_video = compose.get("sourceVideo")
        if not isinstance(source_video, Mapping):
            raise ValueError("video compose sourceVideo must select one source video")
        video_ref = str(
            source_video.get("assetRef") or source_video.get("sourceAssetRef") or ""
        ).strip()
        if not video_ref:
            raise ValueError("video compose sourceVideo assetRef is missing")
        explicit_poster = str(
            source_video.get("posterAssetRef") or compose.get("posterAssetRef") or ""
        ).strip()
        poster_ref = _video_poster_ref(
            video_ref,
            explicit_poster,
            root=root,
            source_assets=source_assets,
        )
        refs = [video_ref, poster_ref]
    elif lane == "article":
        refs = _compose_asset_refs(compose.get("assets"))
    else:
        payload = compose.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("homepage compose payload must be an object")
        raw_bindings = payload.get("imagePlaceholderBindings")
        if raw_bindings is None or raw_bindings == []:
            refs = []
        elif not isinstance(raw_bindings, list):
            raise ValueError("homepage imagePlaceholderBindings must be an array")
        else:
            refs = []
            for raw in raw_bindings:
                if not isinstance(raw, Mapping):
                    raise ValueError("homepage media binding must be an object")
                ref = str(
                    raw.get("sourceAssetRef") or raw.get("assetRef") or ""
                ).strip()
                if not ref:
                    raise ValueError("homepage media binding lacks source asset ref")
                refs.append(ref)
    return _assert_selected_source_asset_refs(refs, root=root, obj=obj)


def verify_stage_artifacts(
    *,
    execution_id: str,
    publish_root: Path = PUBLISH_ROOT,
    release_root: Path = RELEASE_ROOT,
    commercial: bool = True,
    through: str | None = None,
) -> dict[str, Any]:
    """只校验当前 ``through`` 阶段及其直接 predecessor。"""
    del commercial  # verifier is release-class-neutral
    if through is not None and through not in STAGES:
        raise ValueError(f"unsupported --through stage: {through}")
    root = execution_root(execution_id)
    issues: list[str] = []
    if through is not None:
        retired_names = {
            "author_self_check.json",
            "agent_result_envelope.json",
            "draft_meta.json",
            "rubric_review.json",
            "reviewer_result.json",
            "media_ref_review.json",
            "attestation.json",
            "evidence_index.json",
            "finalization_report.json",
        }
        for retired in root.rglob("*") if root.is_dir() else ():
            if retired.is_file() and retired.name in retired_names:
                issues.append(f"execution: retired process artifact forbidden: {retired}")
    object_count = 0
    checked_artifacts = 0
    current_stage = through
    predecessor = (
        STAGES[STAGES.index(through) - 1]
        if through in STAGES and STAGES.index(through) > 0
        else None
    )
    stages_to_check = tuple(stage for stage in (predecessor, current_stage) if stage)

    for obj in _object_roots(root, through):
        object_count += 1
        rel = obj.relative_to(root)
        object_ref = rel.as_posix()
        if not obj.is_dir():
            issues.append(f"{rel}: declared target object directory missing")
            continue
        has_compose = (obj / _COMPOSE_HOMEPAGE_REL).is_file() or (obj / _COMPOSE_PACK_REL).is_file()
        lane = _object_lane(obj) if has_compose else (
            "homepage" if object_ref.startswith("entities/") else object_ref.split("/", 2)[1]
        )
        required = required_stage_artifacts(lane)
        for stage in stages_to_check:
            for name in required.get(stage, ()):
                path = obj / stage / name
                if not path.is_file():
                    issues.append(f"{rel}: missing {stage}/{name}")
                else:
                    checked_artifacts += 1
                    if path.suffix != ".json" and path.stat().st_size == 0:
                        issues.append(f"{rel}/{stage}/{name}: artifact is empty")
        if through is None:
            for final_rel in required_final_artifacts(lane):
                if not (obj / final_rel).is_file():
                    issues.append(f"{rel}: missing final/{final_rel}")

        for relative, schema in _SCHEMA_FILES.items():
            stage = relative.split("/", 1)[0]
            if current_stage is not None and stage not in stages_to_check:
                continue
            path = obj / relative
            if not path.is_file():
                continue
            payload = _validate_json(path, schema, issues)
            artifact_execution_id = str(payload.get("executionId") or "")
            if artifact_execution_id != execution_id:
                issues.append(
                    f"{rel}/{relative}: executionId drift {artifact_execution_id or '<empty>'} != {execution_id}"
                )
            if schema.requires_frozen_binding and payload.get("executionBinding") != "frozen":
                issues.append(f"{rel}/{relative}: artifact must bind frozen execution")

        if through == "1.download":
            source_refs_path = obj / "1.download/source_refs.json"
            if source_refs_path.is_file():
                try:
                    source_refs = read_json(source_refs_path)
                    assert_valid(
                        source_refs,
                        "source",
                        "object_source_refs",
                        label=source_refs_path.as_posix(),
                    )
                except Exception as exc:  # noqa: BLE001
                    issues.append(f"{rel}: source refs invalid ({exc})")
                    source_refs = {}
                if source_refs.get("executionId") != execution_id or source_refs.get("objectRef") != object_ref:
                    issues.append(f"{rel}: source refs identity drift")
                for row in source_refs.get("sources") or []:
                    if not isinstance(row, Mapping):
                        issues.append(f"{rel}: source ref row must be object")
                        continue
                    issues.extend(
                        f"{rel}: {issue}"
                        for issue in _download_source_issues(root, row)
                    )

        if through == "2.quality":
            source_refs_path = obj / "1.download/source_refs.json"
            quality_path = obj / "2.quality/quality_analysis.json"
            if source_refs_path.is_file() and quality_path.is_file():
                source_refs = read_json(source_refs_path)
                quality = read_json(quality_path)
                binding = quality.get("sourceRefs")
                if not _direct_ref(
                    binding,
                    expected_ref="1.download/source_refs.json",
                    expected_digest=_digest(source_refs_path),
                ):
                    issues.append(f"{rel}/2.quality: source_refs exact binding drift")
                issues.extend(
                    f"{rel}/2.quality: {issue}"
                    for issue in _quality_anchor_issues(root, source_refs, quality)
                )

        if through == "3.compose":
            quality_path = obj / "2.quality/quality_analysis.json"
            compose_path = obj / (
                _COMPOSE_HOMEPAGE_REL if lane == "homepage" else _COMPOSE_PACK_REL
            )
            if quality_path.is_file() and compose_path.is_file():
                quality = read_json(quality_path)
                compose = read_json(compose_path)
                if (
                    compose.get("qualityRef") != "2.quality/quality_analysis.json"
                    or compose.get("qualityDigest") != _digest(quality_path)
                ):
                    issues.append(f"{rel}/3.compose: quality exact binding drift")
                retained = _selected_source_ids(quality)
                selected = _compose_source_ids(compose)
                if not selected:
                    issues.append(f"{rel}/3.compose: selectedSourceRefs must name retained source IDs")
                elif not selected.issubset(retained):
                    issues.append(f"{rel}/3.compose: compose references non-retained source IDs")

        if through == "4.draft":
            draft_name = required["4.draft"][0]
            draft_path = obj / "4.draft" / draft_name
            compose_path = obj / (_COMPOSE_HOMEPAGE_REL if lane == "homepage" else _COMPOSE_PACK_REL)
            if draft_path.is_file() and compose_path.is_file():
                issues.extend(
                    f"{rel}/4.draft: {issue}"
                    for issue in _draft_binding_issues(root, obj, lane=lane, object_ref=object_ref)
                )

        if through == "5.review":
            review_path = obj / "5.review/content_review.json"
            if review_path.is_file():
                review = read_json(review_path)
                draft_name = required["4.draft"][0]
                draft_path = obj / "4.draft" / draft_name
                if review.get("objectRef") != object_ref:
                    issues.append(f"{rel}/5.review: content_review object binding drift")
                if draft_path.is_file() and not _direct_ref(
                    review.get("draft"),
                    expected_ref=f"4.draft/{draft_name}",
                    expected_digest=_digest(draft_path),
                ):
                    issues.append(f"{rel}/5.review: draft exact binding drift")
                try:
                    if lane == "homepage":
                        from content.release.canonical.entity_transaction_sources import source_assets_by_ref
                        source_assets = source_assets_by_ref(root)
                    else:
                        from content.release.canonical.post_transaction_assets import source_assets as load_source_assets
                        source_assets = load_source_assets(root)
                    compose_path = obj / (
                        _COMPOSE_HOMEPAGE_REL if lane == "homepage" else _COMPOSE_PACK_REL
                    )
                    compose = read_json(compose_path)
                    draft = read_json(draft_path) if draft_path.suffix == ".json" else {}
                    required_asset_refs = _review_asset_refs(
                        root=root,
                        obj=obj,
                        lane=lane,
                        draft=draft,
                        compose=compose,
                        source_assets=source_assets,
                    )
                    from content.release.canonical.review_rights_binding import validate_content_review_document
                    validate_content_review_document(
                        review,
                        execution_id=execution_id,
                        object_ref=object_ref,
                        required_asset_refs=required_asset_refs,
                        source_assets=source_assets,
                        require_approved=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    issues.append(f"{rel}/5.review: {exc}")

    issues.extend(_boundary_issues(Path(publish_root), root_kind="publish"))
    issues.extend(_boundary_issues(Path(release_root), root_kind="release"))
    return {
        "schema": "quwoquan_data.stage_artifact_verification",
        "executionId": execution_id,
        "executionRoot": str(root),
        "objectCount": object_count,
        "checkedArtifacts": checked_artifacts,
        "commercial": False,
        "through": through,
        "issues": issues,
        "passed": not issues,
    }
