"""对象阶段截止闭包与 publish 后 final artifact 闭包门。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.production_contracts import validate_agent_result_envelope
from core.io import read_json
from core.paths import PUBLISH_ROOT, RELEASE_ROOT, execution_root
from core.schema import assert_valid
from core.stage_artifact_contract import (
    COMMON_STAGE_ARTIFACTS,
    PROCESS_ARTIFACT_NAMES,
    SOURCE_UNIT_ARTIFACTS,
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
    "4.draft/draft_meta.json": ArtifactSchema("content", "draft_meta", True),
    "4.draft/author_self_check.json": ArtifactSchema("content", "author_self_check"),
    "4.draft/agent_result_envelope.json": ArtifactSchema("content", "agent_result_envelope"),
    "4.draft/video_script.json": ArtifactSchema("content", "video_script"),
    "5.review/reviewer_result.json": ArtifactSchema("content", "reviewer_result", True),
    "5.review/media_ref_review.json": ArtifactSchema("content", "media_ref_review"),
    "5.review/attestation.json": ArtifactSchema("content", "review_attestation", True),
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
        if path.is_file() and path.name in PROCESS_ARTIFACT_NAMES:
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


def _review_identity_issues(
    execution_root_path: Path,
    *,
    object_ref: str,
    reviewer_result: dict[str, Any],
    attestation: dict[str, Any],
) -> list[str]:
    """核验 reviewer 独立于作者会话，模型族只保留为真实审计字段。"""
    issues: list[str] = []
    if str(reviewer_result.get("objectRef") or "").strip().strip("/") != object_ref.strip("/"):
        issues.append("reviewer_result.objectRef 与对象路径不一致")
    if str(attestation.get("objectRef") or "").strip().strip("/") != object_ref.strip("/"):
        issues.append("attestation.objectRef 与对象路径不一致")
    reviewer_actor = reviewer_result.get("actor")
    reviewer_actor = reviewer_actor if isinstance(reviewer_actor, dict) else {}
    attested_actor = (attestation.get("independentReviewer") or {}).get("actor")
    attested_actor = attested_actor if isinstance(attested_actor, dict) else {}
    if reviewer_actor != attested_actor:
        issues.append("reviewer_result.actor 与 attestation independentReviewer.actor 不一致")

    receipt_path = execution_root_path / "_shared/receipts/006-4.draft.json"
    if not receipt_path.is_file():
        issues.append("缺少 4.draft receipt，无法证明 reviewer 独立于作者")
        return issues
    try:
        draft_receipt = read_json(receipt_path)
    except (OSError, ValueError, TypeError) as exc:
        issues.append(f"4.draft receipt 不可读取 ({exc})")
        return issues
    author_actor = draft_receipt.get("actor")
    author_actor = author_actor if isinstance(author_actor, dict) else {}
    author_invocation = author_actor.get("invocation")
    author_invocation = author_invocation if isinstance(author_invocation, dict) else {}
    reviewer_invocation = reviewer_actor.get("invocation")
    reviewer_invocation = reviewer_invocation if isinstance(reviewer_invocation, dict) else {}
    if not author_actor:
        issues.append("4.draft receipt 缺少 author actor")
    if not reviewer_actor:
        issues.append("reviewer_result 缺少 reviewer actor")
    if reviewer_actor and author_actor and (
        reviewer_actor.get("host"),
        reviewer_actor.get("sessionId"),
    ) == (author_actor.get("host"), author_actor.get("sessionId")):
        issues.append("reviewer 与作者使用同一 host/sessionId，禁止作者自评")
    author_run_id = str(author_invocation.get("runId") or "").strip()
    reviewer_run_id = str(reviewer_invocation.get("runId") or "").strip()
    if not author_run_id or not reviewer_run_id:
        issues.append("author/reviewer invocation.runId 必须是真实非空记录")
    elif author_run_id == reviewer_run_id:
        issues.append("reviewer 与作者 invocation.runId 相同，禁止作者自评")
    return issues


def _video_rights_coverage_issues(
    execution_root_path: Path,
    *,
    object_root: Path,
    media_review: dict[str, Any],
) -> list[str]:
    """Require review rights rows for every indexed video and poster asset."""
    issues: list[str] = []
    refs_path = object_root / "1.download/source_refs.json"
    if not refs_path.is_file():
        return issues
    source_refs = read_json(refs_path)
    required: dict[str, dict[str, Any]] = {}
    for source in source_refs.get("sources") or []:
        if not isinstance(source, dict):
            continue
        meta_ref = str(source.get("metaRef") or "").strip()
        if not meta_ref.startswith("sources/"):
            continue
        index_path = (execution_root_path / meta_ref).parent / "assets/index.json"
        if not index_path.is_file():
            continue
        for asset in read_json(index_path).get("assets") or []:
            if not isinstance(asset, dict) or asset.get("assetRole") not in {"video", "poster"}:
                continue
            file_name = str(asset.get("fileName") or "").strip()
            if not file_name:
                continue
            asset_ref = (index_path.parent / file_name).relative_to(execution_root_path).as_posix()
            required[asset_ref] = asset
    reviews = {
        str(row.get("assetRef") or "").strip(): row
        for row in media_review.get("rightsReviews") or []
        if isinstance(row, dict)
    }
    for asset_ref, asset in sorted(required.items()):
        review = reviews.get(asset_ref)
        if review is None:
            issues.append(f"media rights review 未覆盖 {asset.get('assetRole')} asset: {asset_ref}")
            continue
        expected = {
            "sourceUrl": asset.get("sourceUrl"),
            "license": asset.get("license"),
            "termsUrl": asset.get("termsUrl"),
            "authorizationProof": asset.get("authorizationProof") or None,
        }
        drift = [field for field, value in expected.items() if review.get(field) != value]
        if drift:
            issues.append(f"media rights review 与 acquisition rights 漂移 {asset_ref}: {','.join(drift)}")
        if review.get("passed") is not True:
            issues.append(f"media rights review 未通过: {asset_ref}")
    return issues


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


def verify_stage_artifacts(
    *,
    execution_id: str,
    publish_root: Path = PUBLISH_ROOT,
    release_root: Path = RELEASE_ROOT,
    commercial: bool = True,
    through: str | None = None,
) -> dict[str, Any]:
    """校验到显式对象阶段；省略 ``through`` 时校验 publish 后 final 闭包。"""
    if through is not None and through not in STAGES:
        raise ValueError(f"unsupported --through stage: {through}")
    root = execution_root(execution_id)
    issues: list[str] = []
    object_count = 0
    checked_artifacts = 0
    stage_cut = (
        tuple(STAGES)
        if through is None
        else tuple(STAGES[: STAGES.index(through) + 1])
    )

    for obj in _object_roots(root, through):
        object_count += 1
        rel = obj.relative_to(root)
        if not obj.is_dir():
            issues.append(f"{rel}: declared target object directory missing")
        has_compose = (obj / _COMPOSE_HOMEPAGE_REL).is_file() or (
            obj / _COMPOSE_PACK_REL
        ).is_file()
        lane = _object_lane(obj) if has_compose else None
        required = (
            required_stage_artifacts(lane)
            if lane is not None
            else {stage: COMMON_STAGE_ARTIFACTS.get(stage, ()) for stage in STAGES}
        )
        for stage in stage_cut:
            for name in required.get(stage, ()):
                path = obj / stage / name
                if not path.is_file():
                    issues.append(f"{rel}: missing {stage}/{name}")
                else:
                    checked_artifacts += 1
        if through is None:
            for final_rel in required_final_artifacts(lane):
                if not (obj / final_rel).is_file():
                    issues.append(f"{rel}: missing final/{final_rel}")
        for relative, schema in _SCHEMA_FILES.items():
            path = obj / relative
            if not path.is_file():
                continue
            payload = _validate_json(path, schema, issues)
            for field in _IDENTITY_FIELDS:
                if not str(payload.get(field) or "").strip():
                    issues.append(f"{rel}/{relative}: identity field missing {field}")
            artifact_execution_id = str(payload.get("executionId") or "")
            if execution_id and artifact_execution_id != execution_id:
                issues.append(
                    f"{rel}/{relative}: executionId drift "
                    f"{artifact_execution_id or '<empty>'} != {execution_id}"
                )
            if commercial and schema.requires_frozen_binding and payload.get("executionBinding") != "frozen":
                issues.append(f"{rel}/{relative}: commercial artifact must bind frozen execution")
            if relative == "4.draft/agent_result_envelope.json":
                envelope_issues = validate_agent_result_envelope(
                    payload,
                    workspace_root=path.parent,
                )
                issues.extend(f"{rel}/{relative}: {issue}" for issue in envelope_issues)
        if "5.review" in stage_cut:
            reviewer_path = obj / "5.review/reviewer_result.json"
            attestation_path = obj / "5.review/attestation.json"
            media_review_path = obj / "5.review/media_ref_review.json"
            if lane == "video" and media_review_path.is_file():
                media_review = read_json(media_review_path)
                issues.extend(
                    f"{rel}/5.review: {issue}"
                    for issue in _video_rights_coverage_issues(
                        root,
                        object_root=obj,
                        media_review=media_review,
                    )
                )
            if reviewer_path.is_file() and attestation_path.is_file():
                reviewer_result = read_json(reviewer_path)
                attestation = read_json(attestation_path)
                issues.extend(
                    f"{rel}/5.review: {issue}"
                    for issue in _review_identity_issues(
                        root,
                        object_ref=rel.as_posix(),
                        reviewer_result=reviewer_result,
                        attestation=attestation,
                    )
                )
        source_refs_path = obj / "1.download/source_refs.json"
        if source_refs_path.is_file():
            try:
                source_refs = read_json(source_refs_path)
            except (OSError, ValueError, TypeError) as exc:
                issues.append(f"{rel}: source refs unreadable ({exc})")
                source_refs = {}
            rows = source_refs.get("sources") if isinstance(source_refs, dict) else None
            if not isinstance(rows, list) or not rows:
                issues.append(f"{rel}: source refs must contain accepted source units")
                rows = []
            for row in rows:
                if not isinstance(row, dict):
                    issues.append(f"{rel}: source ref row must be object")
                    continue
                meta_ref = str(row.get("metaRef") or "").strip()
                source_ref = str(row.get("sourceRef") or "").strip()
                if not meta_ref.startswith("sources/") or not source_ref.startswith("sources/"):
                    issues.append(f"{rel}: source refs must resolve from canonical sources/: {meta_ref or source_ref or '<empty>'}")
                    continue
                meta_path = root / meta_ref
                source_path = root / source_ref
                try:
                    meta_path.resolve().relative_to(root.resolve())
                    source_path.resolve().relative_to(root.resolve())
                except ValueError:
                    issues.append(f"{rel}: source ref escapes execution root: {meta_ref or source_ref}")
                    continue
                if not meta_path.is_file() or not source_path.is_file():
                    issues.append(f"{rel}: unresolved source ref {meta_ref or source_ref}")
                    continue
                if source_path.parent != meta_path.parent:
                    issues.append(f"{rel}: source/meta refs must belong to one source unit: {meta_ref}")
                    continue
                raw_meta = read_json(meta_path)
                atomic = isinstance(raw_meta, dict) and raw_meta.get("schema") == "quwoquan_data.atomic_source_unit"
                required_unit_artifacts = (
                    ("meta.json", "source.md", "snapshot.raw", "assets/index.json")
                    if atomic and not isinstance(raw_meta.get("acquisition"), dict)
                    else (("meta.json", "source.md", "snapshot.bin", "assets/index.json") if atomic else SOURCE_UNIT_ARTIFACTS)
                )
                for unit_rel in required_unit_artifacts:
                    if not (meta_path.parent / unit_rel).is_file():
                        issues.append(f"{rel}: source unit incomplete {meta_path.parent.name}/{unit_rel}")
                meta = _validate_json(
                    meta_path,
                    ("source", "atomic_source_unit_meta" if atomic else "source_unit_meta"),
                    issues,
                )
                if execution_id and str(meta.get("executionId") or "") != execution_id:
                    issues.append(f"{rel}: source meta executionId drift: {meta_ref}")
                expected_unit_id = str(row.get("sourceUnitId") or "").strip()
                actual_unit_id = str(meta.get("sourceUnitId") or "").strip()
                if not expected_unit_id or expected_unit_id != actual_unit_id:
                    issues.append(f"{rel}: source unit identity drift: {meta_ref}")
        # review 通过性是完成型断言：显式截止到 5.review 或执行
        # publish 后 final 闭包时适用；更早阶段可能存在尚未生效的 review 产物。
        attestation_path = obj / "5.review/attestation.json"
        if commercial and "5.review" in stage_cut and attestation_path.is_file():
            attestation = read_json(attestation_path)
            reviewer_status = str((attestation.get("independentReviewer") or {}).get("status") or "")
            if reviewer_status != "passed":
                issues.append(f"{rel}: independent reviewer not passed ({reviewer_status or 'missing'})")
            if attestation.get("decision") != "approved":
                issues.append(f"{rel}: review decision is not approved")

    issues.extend(_boundary_issues(Path(publish_root), root_kind="publish"))
    issues.extend(_boundary_issues(Path(release_root), root_kind="release"))
    return {
        "schema": "quwoquan_data.stage_artifact_verification",
        "executionId": execution_id,
        "executionRoot": str(root),
        "objectCount": object_count,
        "checkedArtifacts": checked_artifacts,
        "commercial": commercial,
        "through": through,
        "issues": issues,
        "passed": not issues,
    }
