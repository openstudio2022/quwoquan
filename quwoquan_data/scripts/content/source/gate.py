"""Exit gate for download command."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.control_types import ContentType
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.image_asset_strategy import (
    image_count_is_hard_quota,
    image_strategy_requires_publishable_images,
)
from core.io import read_json
from governance.coverage.license import rights_proof_required

from content.execution.identity import parse_execution_id
from content.execution.workspace import execution_command_root, execution_root

PRIMARY_SOURCE_MINIMUM = 1


@dataclass(frozen=True, slots=True)
class DownloadRequirements:
    min_sources: int
    min_images: int
    min_article_base_sources: int
    min_homepage_sources: int
    min_homepage_media: int


def _validate_execution_identity(execution_id: str) -> None:
    parse_execution_id(execution_id)


def download_requirements(execution_id: str) -> DownloadRequirements:
    """Derive download gates from the admitted single-carrier execution spec."""
    from content.execution import store

    parse_execution_id(execution_id)
    spec = store.load_spec_model(execution_id)
    content_type = spec.content.carriers[0]
    quota = spec.content.quotas.for_type(content_type)
    min_homepage_sources = (
        PRIMARY_SOURCE_MINIMUM if content_type is ContentType.HOMEPAGE else 0
    )
    min_article_sources = quota if content_type is ContentType.ARTICLE else 0
    minimum_publishable_images = (
        spec.content.research.minimum_publishable_images_per_target or 0
    )
    min_images = 0
    if content_type is ContentType.IMAGE and image_strategy_requires_publishable_images(
        spec.to_dict()
    ):
        min_images = (
            max(quota, minimum_publishable_images)
            if image_count_is_hard_quota(spec.to_dict())
            else minimum_publishable_images
        )
    min_homepage_media = (
        minimum_publishable_images
        if content_type is ContentType.HOMEPAGE
        and image_strategy_requires_publishable_images(spec.to_dict())
        else 0
    )
    return DownloadRequirements(
        min_sources=max(min_homepage_sources, min_article_sources),
        min_images=min_images,
        min_article_base_sources=min_article_sources,
        min_homepage_sources=min_homepage_sources,
        min_homepage_media=min_homepage_media,
    )



def active_download_lanes(execution_id: str) -> frozenset[str]:
    """Return the single admitted research lane from the execution spec."""
    from content.execution import store

    spec = store.load_spec_model(execution_id)
    return frozenset(lane.value for lane in spec.content.research.lanes)


def _text_lanes_required(execution_id: str) -> bool:
    lanes = active_download_lanes(execution_id)
    return bool(lanes & {ContentType.HOMEPAGE.value, ContentType.ARTICLE.value})


def _source_roots(execution_id: str) -> tuple[Path, list[Path]]:
    from content.source.source_unit import iter_source_units

    _validate_execution_identity(execution_id)
    object_root = execution_root(execution_id) / "entities"
    if object_root.is_dir():
        object_dirs = [
            p.parent.parent
            for p in object_root.rglob("1.download/source_refs.json")
            if p.is_file() and iter_source_units(p.parent.parent)
        ]
        if object_dirs:
            return object_root, sorted(set(object_dirs))

    return object_root, []



def _entity_from_sources_dir(root: Path, sources_dir: Path) -> str:
    try:
        rel = sources_dir.relative_to(root)
    except ValueError:
        return ""
    parts = rel.parts
    if "1.download" in parts:
        index = parts.index("1.download")
        if index > 0:
            return parts[index - 1]
    if len(parts) >= 3:
        return parts[-1]
    return ""


def _missing_sources_label(root: Path, entity: str) -> str:
    for candidate in root.glob(f"*/*/{entity}"):
        if candidate.is_dir():
            try:
                return (candidate / "1.download" / "source_refs.json").relative_to(root).as_posix()
            except ValueError:
                break
    return f"{entity}/1.download/source_refs.json"


def _homepage_base_ready(
    execution_id: str,
    batch_dir: Path,
    source_dir: Path,
    meta: dict,
    entity: str,
) -> bool:
    if str(meta.get("researchLane") or "") != "homepage":
        return False
    source_path = source_dir / "source.md"
    if not source_path.is_file():
        return False
    try:
        from content.homepage.homepage_text import load_homepage_base_draft_text

        source_ref = source_path.resolve().relative_to(batch_dir.resolve()).as_posix()
        text = load_homepage_base_draft_text(execution_id, source_ref)
    except Exception:  # noqa: BLE001
        return False
    try:
        from content.homepage.homepage_text import homepage_base_draft_readiness
        from content.homepage.quality_policy import (
            homepage_body_char_minimum,
            homepage_fact_char_minimum,
            homepage_fact_count_minimum,
        )

        # source_dir 即 source unit 目录：传 unit_dir 让 homepage_source_judge
        # 消费已写回的 source.judge.json（灰区无 verdict 时 fail-closed）。
        qualified_authority_title = str(
            meta.get("qualifiedAuthorityTitle") or ""
        ).strip()
        verdict = homepage_base_draft_readiness(
            meta,
            text,
            entity_name=entity,
            aliases=(qualified_authority_title,) if qualified_authority_title else (),
            unit_dir=source_dir,
            minimum_body_chars=homepage_body_char_minimum(execution_id),
            minimum_fact_count=homepage_fact_count_minimum(execution_id),
            minimum_fact_chars=homepage_fact_char_minimum(execution_id),
        )
    except Exception:  # noqa: BLE001
        return False
    return bool(verdict.get("ready"))


def _stage_gate_report_issues(
    execution_id: str,
    *,
    target_entities: set[str] | None = None,
    text_lanes_required: bool = True,
) -> list[DataIssue]:
    _validate_execution_identity(execution_id)
    result_root = execution_command_root(execution_id, "source") / "results"
    issues: list[DataIssue] = []
    for step in (
        "source_plan_gate",
        "image_rights_gate",
        "image_fetch_gate",
        "entity_source_bundle_gate",
    ):
        step_dir = result_root / step
        if not step_dir.is_dir():
            continue
        for path in sorted(step_dir.glob("*.json")):
            try:
                data = read_json(path)
            except Exception:  # noqa: BLE001, S112
                continue
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
            if not isinstance(payload, dict) or payload.get("passed") is not False:
                continue
            ref = str(payload.get("ref") or path.stem)
            if target_entities is not None and ref not in target_entities:
                continue
            raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
            if raw_issues:
                for raw_issue in raw_issues:
                    if not isinstance(raw_issue, dict):
                        raise TypeError(
                            f"retired untyped download gate report: {path}; rerun download to regenerate"
                        )
                    issue = DataIssue.from_dict(raw_issue)
                    if (
                        step == "entity_source_bundle_gate"
                        and not text_lanes_required
                        and issue.code is DataIssueCode.SOURCE_RETAINED_SHORTFALL
                    ):
                        continue
                    issues.append(issue if issue.ref else data_issue(
                        issue.code,
                        stage=issue.stage,
                        ref=ref,
                        lane=issue.lane,
                        recovery=issue.recovery,
                        message=issue.message,
                        attributes=dict(issue.attributes),
                    ))
            else:
                issues.append(data_issue(
                    _STAGE_DEFAULT_ISSUE_CODE[step],
                    stage=_STAGE_DEFAULT_ISSUE_STAGE[step],
                    ref=ref,
                    message=f"{step} failed without issue detail",
                ))
    return issues


_STAGE_DEFAULT_ISSUE_CODE = {
    "source_plan_gate": DataIssueCode.SOURCE_PLAN_INVALID,
    "image_rights_gate": DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
    "image_fetch_gate": DataIssueCode.MEDIA_FETCH_FAILED,
    "entity_source_bundle_gate": DataIssueCode.SOURCE_RETAINED_SHORTFALL,
}
_STAGE_DEFAULT_ISSUE_STAGE = {
    "source_plan_gate": DataIssueStage.SOURCE_PLAN,
    "image_rights_gate": DataIssueStage.IMAGE_RIGHTS,
    "image_fetch_gate": DataIssueStage.IMAGE_FETCH,
    "entity_source_bundle_gate": DataIssueStage.ENTITY_SOURCE_BUNDLE,
}


def gate_download(execution_id: str, *, target_entities: set[str] | None = None) -> list[DataIssue]:
    """Check download exit criteria.

    只检查对象树 `entities/**/1.download/source_refs.json` 指向的 canonical source units。
    """
    issues: list[DataIssue] = []
    require_rights_proof = rights_proof_required(
        parse_execution_id(execution_id).vertical
    )
    requirements = download_requirements(execution_id)
    active_lanes = active_download_lanes(execution_id)
    text_lanes_required = _text_lanes_required(execution_id)
    root, sources_dirs = _source_roots(execution_id)
    if not sources_dirs:
        if target_entities:
            for entity in sorted(target_entities):
                issues.append(data_issue(
                    DataIssueCode.SOURCE_MISSING,
                    stage=DataIssueStage.DOWNLOAD_FETCH,
                    ref=entity,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message=f"{_missing_sources_label(root, entity)}: sources directory missing",
                ))
            issues.extend(
                _stage_gate_report_issues(
                    execution_id,
                    target_entities=target_entities,
                    text_lanes_required=text_lanes_required,
                )
            )
            return issues
        issues.append(data_issue(
            DataIssueCode.SOURCE_MISSING,
            stage=DataIssueStage.DOWNLOAD_FETCH,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            message=f"No source_refs.json under {root}",
        ))
        issues.extend(
            _stage_gate_report_issues(
                execution_id,
                target_entities=target_entities,
                text_lanes_required=text_lanes_required,
            )
        )
        return issues

    source_entities = {_entity_from_sources_dir(root, path) for path in sources_dirs}
    if target_entities is not None:
        for entity in sorted(target_entities):
            if entity and entity not in source_entities:
                issues.append(data_issue(
                    DataIssueCode.SOURCE_MISSING,
                    stage=DataIssueStage.DOWNLOAD_FETCH,
                    ref=entity,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message=f"{_missing_sources_label(root, entity)}: sources directory missing",
                ))
    batch_dir = root.parent
    for sources_dir in sources_dirs:
        from content.source.source_unit import iter_source_units

        entity = _entity_from_sources_dir(root, sources_dir)
        if target_entities is not None and entity not in target_entities:
            continue
        source_units = iter_source_units(sources_dir)
        md_count = 0
        retained_count = 0
        lane_md_count = {"homepage": 0, "article": 0}
        lane_retained_count = {"homepage": 0, "article": 0}
        homepage_base_ready_count = 0
        image_hashes: set[str] = set()
        image_rights_issues: list[str] = []
        for sd in source_units:
            meta_path = sd / "meta.json"
            try:
                meta = read_json(meta_path) if meta_path.is_file() else {}
            except Exception:  # noqa: BLE001
                meta = {}
            lane = str(meta.get("researchLane") or "")
            is_image_unit = lane in {"image", "homepage_image"}
            if (sd / "source.md").exists() and not is_image_unit:
                md_count += 1
                if lane in lane_md_count:
                    lane_md_count[lane] += 1
            quality_path = sd / "source.quality.json"
            if not quality_path.is_file():
                continue
            try:
                payload = read_json(quality_path)
            except Exception:  # noqa: BLE001, S112
                continue
            if str(payload.get("quality") or "") != "Reject" and not is_image_unit:
                retained_count += 1
                if lane in lane_retained_count:
                    lane_retained_count[lane] += 1
                if _homepage_base_ready(execution_id, batch_dir, sd, meta, entity):
                    homepage_base_ready_count += 1
            index_path = sd / "assets" / "index.json"
            source_assets: list[dict] = []
            if index_path.is_file():
                try:
                    source_assets = read_json(index_path).get("assets") or []
                except Exception:  # noqa: BLE001
                    source_assets = []
            # Text-source snapshots may retain inline images as provenance, but
            # they are not image-lane publication candidates. They must neither
            # satisfy the independent image quota nor block the text carrier on
            # media-rights fields.
            if is_image_unit:
                for asset in source_assets:
                    if not isinstance(asset, dict):
                        continue
                    digest = str(asset.get("sha256") or asset.get("sourceAssetId") or "")
                    if digest:
                        image_hashes.add(digest)
                    from governance.coverage.distribution import (
                        asset_contract_missing_fields,
                    )

                    missing = asset_contract_missing_fields(asset)
                    if require_rights_proof:
                        missing.extend(
                            field
                            for field in (
                                "license",
                                "credit",
                                "sourceUrl",
                                "termsUrl",
                                "usageScope",
                            )
                            if not str(asset.get(field) or "").strip()
                        )
                    missing = sorted(set(missing))
                    if missing:
                        image_rights_issues.append(
                            f"{sd.name}/{asset.get('fileName') or '?'} missing image rights {missing}"
                        )
        rel_obj = sources_dir.relative_to(root).as_posix() if sources_dir.is_relative_to(root) else sources_dir.name
        rel = f"{rel_obj}/1.download/source_refs.json"
        if text_lanes_required and md_count < requirements.min_sources:
            issues.append(data_issue(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                message=f"{rel}: only {md_count} sources (need >= {requirements.min_sources})",
                attributes={"retained": md_count, "required": requirements.min_sources},
            ))
        if text_lanes_required and retained_count < requirements.min_sources:
            issues.append(data_issue(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                message=(
                    f"{rel}: only {retained_count} retained sources "
                    f"(need >= {requirements.min_sources}; Reject/manual probe sources do not count)"
                ),
                attributes={"retained": retained_count, "required": requirements.min_sources},
            ))
        homepage_required = ContentType.HOMEPAGE.value in active_lanes
        if homepage_required and lane_retained_count["homepage"] < 1:
            issues.append(data_issue(
                DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity,
                lane=DataIssueLane.HOMEPAGE,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                message=(
                    f"{rel}: homepage retained sources={lane_retained_count['homepage']} need>=1 "
                    "(homepage lane must yield a readable primary-authority encyclopedia source unit)"
                ),
                attributes={"retained": lane_retained_count["homepage"], "required": 1},
            ))
        elif homepage_required and homepage_base_ready_count < 1:
            issues.append(data_issue(
                DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity,
                lane=DataIssueLane.HOMEPAGE,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                message=(
                    f"{rel}: homepage baseDraft-ready sources={homepage_base_ready_count} need>=1 "
                    "(homepage lane must yield a primary-authority encyclopedia source with the policy minimum usable facts)"
                ),
                attributes={"retained": homepage_base_ready_count, "required": 1},
            ))
        min_article_sources = requirements.min_article_base_sources
        article_required = (
            ContentType.ARTICLE.value in active_lanes and min_article_sources > 0
        )
        if article_required and lane_retained_count["article"] < min_article_sources:
            issues.append(data_issue(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity,
                lane=DataIssueLane.ARTICLE,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                message=(
                    f"{rel}: article retained sources={lane_retained_count['article']} "
                    f"need>={min_article_sources}"
                ),
                attributes={"retained": lane_retained_count["article"], "required": min_article_sources},
            ))
        if len(image_hashes) < requirements.min_images:
            issues.append(data_issue(
                DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity,
                lane=DataIssueLane.IMAGE,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                message=(
                    f"{rel}: only {len(image_hashes)} unique publishable images "
                    f"(need >= {requirements.min_images})"
                ),
                attributes={"retained": len(image_hashes), "required": requirements.min_images},
            ))
        issues.extend(
            data_issue(
                DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity,
                lane=DataIssueLane.IMAGE,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
                message=f"{rel}: {issue}",
            )
            for issue in image_rights_issues
        )

    seen = {str(issue) for issue in issues}
    for issue in _stage_gate_report_issues(
        execution_id,
        target_entities=target_entities,
        text_lanes_required=text_lanes_required,
    ):
        if str(issue) not in seen:
            issues.append(issue)
            seen.add(str(issue))
    return issues
