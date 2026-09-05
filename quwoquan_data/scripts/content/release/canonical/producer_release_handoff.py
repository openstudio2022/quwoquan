"""Create and validate the terminal producer handoff after all release CLOSE receipts."""
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

from content.execution.receipt_chain import (
    ReceiptChainError,
    validate_embedded_receipt_chain,
    validate_live_receipt_chain,
)
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
_PRODUCER_CONTRACT_PATHS = (
    '.agents/skills/content-production/SKILL.md',
    '.agents/skills/content-production/references/boundary.md',
    '.agents/skills/content-production/references/execution-layout.md',
    '.agents/skills/content-production/references/handoff-protocol.md',
    '.agents/skills/content-production/references/orchestration.md',
    '.agents/skills/content-production/references/recovery.md',
    '.agents/skills/content-production/references/stage-contracts/0.plan.md',
    '.agents/skills/content-production/references/stage-contracts/sources.md',
    '.agents/skills/content-production/references/stage-contracts/1.download.md',
    '.agents/skills/content-production/references/stage-contracts/2.quality.md',
    '.agents/skills/content-production/references/stage-contracts/3.compose.md',
    '.agents/skills/content-production/references/stage-contracts/4.draft.md',
    '.agents/skills/content-production/references/stage-contracts/5.review.md',
    '.agents/skills/content-production/references/stage-contracts/publish.md',
    '.agents/skills/content-production/references/stage-contracts/release.md',
    'quwoquan_data/schema/_common/data_issue.schema.json',
    'quwoquan_data/schema/content/content_review.schema.json',
    'quwoquan_data/schema/content/entity_page_input.schema.json',
    'quwoquan_data/schema/content/image_work.schema.json',
    'quwoquan_data/schema/content/post_manifest.schema.json',
    'quwoquan_data/schema/content/quality_analysis.schema.json',
    'quwoquan_data/schema/content/video_script.schema.json',
    'quwoquan_data/schema/content/writing_pack.schema.json',
    'quwoquan_data/schema/execution/carrier_demand.schema.json',
    'quwoquan_data/schema/execution/content_execution_manifest.schema.json',
    'quwoquan_data/schema/execution/immutable_candidate_bindings.schema.json',
    'quwoquan_data/schema/execution/publish_ref.schema.json',
    'quwoquan_data/schema/execution/stage_close_input.schema.json',
    'quwoquan_data/schema/execution/stage_open_request.schema.json',
    'quwoquan_data/schema/execution/stage_receipt.schema.json',
    'quwoquan_data/schema/execution/target_set.schema.json',
    'quwoquan_data/schema/execution/task_init_request.schema.json',
    'quwoquan_data/schema/source/atomic_source_unit_meta.schema.json',
    'quwoquan_data/schema/source/object_source_refs.schema.json',
    'quwoquan_data/schema/source/source_candidate.schema.json',
    'quwoquan_data/schema/source/source_plan.schema.json',
    'quwoquan_data/schema/publish/entity.schema.json',
    'quwoquan_data/schema/release/asset_rights_closure.schema.json',
    'quwoquan_data/schema/release/content_pool_handoff_query.schema.json',
    'quwoquan_data/schema/release/media_manifest.schema.json',
    'quwoquan_data/schema/release/object_transaction_package.schema.json',
    'quwoquan_data/schema/release/pool_object_record.schema.json',
    'quwoquan_data/schema/release/producer_release_handoff.schema.json',
    'quwoquan_data/schema/release/release_asset_admission.schema.json',
    'quwoquan_data/schema/release/release_attestation.schema.json',
    'quwoquan_data/schema/release/release_cohort.schema.json',
    'quwoquan_data/schema/release/release_desired_state.schema.json',
    'quwoquan_data/schema/release/release_header.schema.json',
    'quwoquan_data/schema/governance/_definition.schema.json',
    'quwoquan_data/schema/governance/content_distribution_policy.schema.json',
    'quwoquan_data/control_plane/_shared/content_distribution.policy.yaml',
    'quwoquan_data/control_plane/_shared/media_processing.policy.yaml',
    'quwoquan_data/control_plane/_shared/catalogs/content_source_registry.yaml',
    'quwoquan_data/prompts/README.md',
    'quwoquan_data/prompts/_shared/content_independent_review.system.md',
    'quwoquan_data/prompts/_shared/content_independent_review.task.md',
    'quwoquan_data/prompts/_shared/content_independent_review.vars.yaml',
    'quwoquan_data/prompts/_shared/partials/author_source_factual.md',
    'quwoquan_data/prompts/_shared/partials/constraints_fidelity.md',
    'quwoquan_data/prompts/_shared/partials/figure_group_contract.md',
    'quwoquan_data/prompts/_shared/partials/image_placeholder_contract.md',
    'quwoquan_data/prompts/_shared/partials/output_format_article.md',
    'quwoquan_data/prompts/_shared/partials/output_format_homepage.md',
    'quwoquan_data/prompts/_shared/partials/output_format_image.md',
    'quwoquan_data/prompts/article/article_author.system.md',
    'quwoquan_data/prompts/article/article_author.task.md',
    'quwoquan_data/prompts/article/article_author.vars.yaml',
    'quwoquan_data/prompts/homepage/entity_homepage.system.md',
    'quwoquan_data/prompts/homepage/entity_homepage.task.md',
    'quwoquan_data/prompts/homepage/entity_homepage.vars.yaml',
    'quwoquan_data/prompts/homepage/homepage_source_judge.system.md',
    'quwoquan_data/prompts/homepage/homepage_source_judge.task.md',
    'quwoquan_data/prompts/homepage/homepage_source_judge.vars.yaml',
    'quwoquan_data/prompts/image/image_curation.system.md',
    'quwoquan_data/prompts/image/image_curation.task.md',
    'quwoquan_data/prompts/image/image_curation.vars.yaml',
    'quwoquan_data/prompts/video/video_author.system.md',
    'quwoquan_data/prompts/video/video_author.task.md',
    'quwoquan_data/prompts/video/video_author.vars.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/博物馆/体验.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/博物馆/科普.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/古镇/叙事.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/古镇/攻略.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/景区/专业导览.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/景区/体验.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/景区/攻略.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/景区/文化.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/民宿/点评.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/遗址/文化.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/地点/餐厅/探店.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/机构/学校/家长择校.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/机构/学校/新生攻略.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/机构/学校/校园日记.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/机构/学校/校园评测.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/机构/学校/校招就业.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/机构/学校/考研经验.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Entity/机构/学校/选课攻略.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/主题/个人游记.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/主题/地理深读.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/主题/城市漫步.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/主题/摄影机位.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/主题/风物美食.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/合辑/主题合辑.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/榜单/Top榜单.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/周末短途.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/枢纽到达.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/深度探险.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/环线攻略.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/省钱攻略.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/自驾路书.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/补给避险.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/跟团攻略.tmpl.yaml',
    'quwoquan_data/templates/article/blueprints/Format/内容角度/线路/银发慢游.tmpl.yaml',
    'quwoquan_data/templates/image/blueprints/Entity/地点/打卡地/美图.tmpl.yaml',
    'quwoquan_data/templates/image/blueprints/Format/内容角度/主题/图文画报.tmpl.yaml',
    'quwoquan_data/verticals/travel/content_policy.yaml',
    'quwoquan_data/verticals/travel/providers.yaml',
    'quwoquan_data/verticals/travel/rights/license_policy.yaml',
    'quwoquan_data/requirements.txt',
    'quwoquan_data/scripts/content/execution/__init__.py',
    'quwoquan_data/scripts/content/execution/handler.py',
    'quwoquan_data/scripts/content/execution/identity.py',
    'quwoquan_data/scripts/content/execution/production_contracts.py',
    'quwoquan_data/scripts/content/execution/receipt_chain.py',
    'quwoquan_data/scripts/content/execution/runtime_contract.py',
    'quwoquan_data/scripts/content/execution/stage_receipt.py',
    'quwoquan_data/scripts/content/execution/stage_receipt_cli.py',
    'quwoquan_data/scripts/content/execution/task_init.py',
    'quwoquan_data/scripts/content/execution/task_init_cli.py',
    'quwoquan_data/scripts/content/execution/workspace.py',
    'quwoquan_data/scripts/content/source/__init__.py',
    'quwoquan_data/scripts/content/source/acquisition_body_state.py',
    'quwoquan_data/scripts/content/source/atomic_source_cli.py',
    'quwoquan_data/scripts/content/source/atomic_source_io.py',
    'quwoquan_data/scripts/content/source/baike_layout.py',
    'quwoquan_data/scripts/content/source/contracts.py',
    'quwoquan_data/scripts/content/source/fetch_text.py',
    'quwoquan_data/scripts/content/source/host_source_review.py',
    'quwoquan_data/scripts/content/source/html_text.py',
    'quwoquan_data/scripts/content/source/image_payload.py',
    'quwoquan_data/scripts/content/source/media/__init__.py',
    'quwoquan_data/scripts/content/source/media/acquire_images_cli.py',
    'quwoquan_data/scripts/content/source/media/acquire_videos_cli.py',
    'quwoquan_data/scripts/content/source/media_source_admission_contract.py',
    'quwoquan_data/scripts/content/source/mediawiki_page.py',
    'quwoquan_data/scripts/content/source/professional_commons_video_input_evidence.py',
    'quwoquan_data/scripts/content/source/professional_image_acquisition.py',
    'quwoquan_data/scripts/content/source/professional_image_acquisition_binding.py',
    'quwoquan_data/scripts/content/source/professional_image_acquisition_item.py',
    'quwoquan_data/scripts/content/source/professional_image_admission.py',
    'quwoquan_data/scripts/content/source/professional_image_discovery_binding.py',
    'quwoquan_data/scripts/content/source/professional_image_network_admission.py',
    'quwoquan_data/scripts/content/source/professional_image_openverse_contract.py',
    'quwoquan_data/scripts/content/source/professional_image_receipt_counts.py',
    'quwoquan_data/scripts/content/source/professional_image_receipt_validation.py',
    'quwoquan_data/scripts/content/source/professional_image_source_attribution.py',
    'quwoquan_data/scripts/content/source/professional_image_supported_api_contract.py',
    'quwoquan_data/scripts/content/source/professional_image_transport.py',
    'quwoquan_data/scripts/content/source/professional_safety_evidence.py',
    'quwoquan_data/scripts/content/source/professional_video_acquisition.py',
    'quwoquan_data/scripts/content/source/professional_video_asset_acquisition.py',
    'quwoquan_data/scripts/content/source/professional_video_catalog_binding.py',
    'quwoquan_data/scripts/content/source/professional_video_deduplication.py',
    'quwoquan_data/scripts/content/source/professional_video_frozen_asset.py',
    'quwoquan_data/scripts/content/source/professional_video_manual_input_media.py',
    'quwoquan_data/scripts/content/source/professional_video_plan_spec.py',
    'quwoquan_data/scripts/content/source/professional_video_popular_catalog.py',
    'quwoquan_data/scripts/content/source/professional_video_popularity.py',
    'quwoquan_data/scripts/content/source/professional_video_probe.py',
    'quwoquan_data/scripts/content/source/professional_video_provider_batch.py',
    'quwoquan_data/scripts/content/source/professional_video_rebind_historical.py',
    'quwoquan_data/scripts/content/source/professional_video_receipt.py',
    'quwoquan_data/scripts/content/source/professional_video_spec_index.py',
    'quwoquan_data/scripts/content/source/professional_video_store.py',
    'quwoquan_data/scripts/content/source/professional_video_transport.py',
    'quwoquan_data/scripts/content/source/research/__init__.py',
    'quwoquan_data/scripts/content/source/research/baidu_baike.py',
    'quwoquan_data/scripts/content/source/research/baike_com.py',
    'quwoquan_data/scripts/content/source/research/homepage_article_source_attribution.py',
    'quwoquan_data/scripts/content/source/research/image_provider_compliance.py',
    'quwoquan_data/scripts/content/source/research/network_io.py',
    'quwoquan_data/scripts/content/source/research/text_match.py',
    'quwoquan_data/scripts/content/source/rights_decision_projection.py',
    'quwoquan_data/scripts/content/source/source_asset_identity.py',
    'quwoquan_data/scripts/content/source/source_assets.py',
    'quwoquan_data/scripts/content/source/source_snapshot_redaction.py',
    'quwoquan_data/scripts/content/source/source_unit.py',
    'quwoquan_data/scripts/content/source/source_unit_asset_entry.py',
    'quwoquan_data/scripts/content/source/source_unit_attribution.py',
    'quwoquan_data/scripts/content/source/source_unit_manifest_media.py',
    'quwoquan_data/scripts/content/source/source_unit_writer.py',
    'quwoquan_data/scripts/content/source/video_media_probe.py',
    'quwoquan_data/scripts/content/source/video_source_unit_contract.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_builder.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_closure.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_documents.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_existing.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_pool.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_pool_closure.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_result.py',
    'quwoquan_data/scripts/content/release/canonical/aggregate_release_selection.py',
    'quwoquan_data/scripts/content/release/canonical/content_pool_handoff.py',
    'quwoquan_data/scripts/content/release/canonical/content_pool_record.py',
    'quwoquan_data/scripts/content/release/canonical/creator_avatar_quality.py',
    'quwoquan_data/scripts/content/release/canonical/effective_admission.py',
    'quwoquan_data/scripts/content/release/canonical/handler.py',
    'quwoquan_data/scripts/content/release/canonical/handler_pool.py',
    'quwoquan_data/scripts/content/release/canonical/image_identity.py',
    'quwoquan_data/scripts/content/release/canonical/media_holding_closure.py',
    'quwoquan_data/scripts/content/release/canonical/media_library_holding.py',
    'quwoquan_data/scripts/content/release/canonical/object_source_identity.py',
    'quwoquan_data/scripts/content/release/canonical/object_transaction_bindings.py',
    'quwoquan_data/scripts/content/release/canonical/object_transaction_contract.py',
    'quwoquan_data/scripts/content/release/canonical/object_transaction_environment.py',
    'quwoquan_data/scripts/content/release/canonical/object_transaction_lock.py',
    'quwoquan_data/scripts/content/release/canonical/pool_record_history.py',
    'quwoquan_data/scripts/content/release/canonical/pool_source_attribution.py',
    'quwoquan_data/scripts/content/release/canonical/producer_release_handoff.py',
    'quwoquan_data/scripts/content/release/canonical/publish_homepage_object.py',
    'quwoquan_data/scripts/content/release/canonical/publish_object.py',
    'quwoquan_data/scripts/content/release/canonical/release_admission.py',
    'quwoquan_data/scripts/content/release/canonical/release_attestation.py',
    'quwoquan_data/scripts/content/release/canonical/release_consistency.py',
    'quwoquan_data/scripts/content/release/canonical/release_consistency_report.py',
    'quwoquan_data/scripts/content/release/canonical/release_header.py',
    'quwoquan_data/scripts/content/release/canonical/release_media_consistency.py',
    'quwoquan_data/scripts/content/release/canonical/review_rights_binding.py',
    'quwoquan_data/scripts/content/release/canonical/sealed_release_facts.py',
    'quwoquan_data/scripts/core/asset_identity.py',
    'quwoquan_data/scripts/core/content_library.py',
    'quwoquan_data/scripts/core/content_source_registry.py',
    'quwoquan_data/scripts/core/control_types.py',
    'quwoquan_data/scripts/core/image_decode.py',
    'quwoquan_data/scripts/core/image_rules.py',
    'quwoquan_data/scripts/core/image_variants.py',
    'quwoquan_data/scripts/core/io.py',
    'quwoquan_data/scripts/core/media_asset_url.py',
    'quwoquan_data/scripts/core/media_processing_policy.py',
    'quwoquan_data/scripts/core/object_storage_budget.py',
    'quwoquan_data/scripts/core/paths.py',
    'quwoquan_data/scripts/core/release_layout.py',
    'quwoquan_data/scripts/core/release_media_binding.py',
    'quwoquan_data/scripts/core/schema.py',
    'quwoquan_data/scripts/core/source_attribution.py',
    'quwoquan_data/scripts/core/source_digest.py',
    'quwoquan_data/scripts/core/tree_integrity.py',
    'quwoquan_data/scripts/governance/coverage/distribution.py',
    'quwoquan_data/scripts/governance/coverage/license.py',
    'quwoquan_service/services/content-service/contracts/media/media_asset/image_variant_policy.yaml',
)


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


def _validate_current_producer_contract_baseline(
    revision: object, *, repo_root: Path
) -> str:
    value = _validate_producer_baseline_revision(revision, repo_root=repo_root)
    diff = _git("diff", "--quiet", value, "--", *_PRODUCER_CONTRACT_PATHS, repo_root=repo_root)
    if diff.returncode == 1:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_DRIFT", value)
    if diff.returncode != 0:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_INVALID", diff.stderr.strip())
    status = _git(
        "status", "--porcelain", "--untracked-files=all", "--",
        *_PRODUCER_CONTRACT_PATHS, repo_root=repo_root
    )
    if status.returncode != 0:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_INVALID", status.stderr.strip())
    if any(line.startswith("?? ") for line in status.stdout.splitlines()):
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_DRIFT", value)
    return value


def _sealed_release_ref_bytes(
    *, binding: Mapping[str, Any], release_id: str, release_root: Path
) -> bytes | None:
    if binding.get("scope") != "output":
        return None
    ref = _safe_ref(binding.get("ref"), label="release receipt ref")
    prefix = f"data/releases/{release_id}/"
    if not ref.startswith(prefix):
        return None
    return _assert_no_symlink(
        release_root / release_id / ref.removeprefix(prefix),
        label=f"sealed release ref:{ref}",
    ).read_bytes()


def _chain_bindings(chain_document: Mapping[str, Any]) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for opened in chain_document.get("openRequests", []):
        if isinstance(opened, Mapping):
            bindings.extend(
                dict(row)
                for row in opened.get("inputRefs", [])
                if isinstance(row, Mapping)
            )
    for receipt in chain_document.get("receipts", []):
        if not isinstance(receipt, Mapping):
            continue
        for field in ("inputRefs", "resultRefs"):
            bindings.extend(
                dict(row)
                for row in receipt.get(field, [])
                if isinstance(row, Mapping)
            )
        for fact in receipt.get("verifierFacts", []):
            evidence = fact.get("evidenceRef") if isinstance(fact, Mapping) else None
            evidence_digest = fact.get("evidenceDigest") if isinstance(fact, Mapping) else None
            if isinstance(evidence, Mapping) and isinstance(evidence_digest, str):
                bindings.append({**dict(evidence), "digest": evidence_digest})
    return bindings


def _frozen_reference_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("scope") or ""),
        str(row.get("ref") or ""),
        str(row.get("digest") or ""),
    )


def _validate_live_execution_chain(
    *,
    execution_id: str,
    execution_root: Path,
    repo_root: Path,
    output_root: Path,
    cohort_binding: Mapping[str, Any],
    header_ref: str,
    header_digest: str,
    release_id: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    omitted = {
        ("output", str(cohort_binding["ref"]), str(cohort_binding["digest"])),
        ("output", header_ref, header_digest),
    }
    try:
        chain = validate_live_receipt_chain(
            execution_id=execution_id,
            execution_root=execution_root,
            repo_root=repo_root,
            output_root=output_root,
            expected_count=9,
            terminal_verdict="pass",
            snapshot_omissions=omitted,
        )
    except ReceiptChainError as exc:
        code = (
            "DATA.RELEASE.HANDOFF_DIGEST_DRIFT"
            if "digest" in str(exc)
            else "DATA.RELEASE.HANDOFF_EXECUTION_CHAIN_INVALID"
        )
        raise _error(code, str(exc)) from exc
    release_open = chain.open_requests[-1]
    terminal = chain.terminal_receipt
    cohort_frozen = {
        "scope": "output",
        "ref": cohort_binding["ref"],
        "digest": cohort_binding["digest"],
    }
    if cohort_frozen not in release_open.get("inputRefs", []):
        raise _error("DATA.RELEASE.HANDOFF_COHORT_OPEN_UNBOUND", execution_id)
    header_binding = {"scope": "output", "ref": header_ref, "digest": header_digest}
    if header_binding not in terminal.get("resultRefs", []):
        raise _error("DATA.RELEASE.HANDOFF_RECEIPT_RELEASE_UNBOUND", execution_id)
    release_prefix = f"data/releases/{release_id}/"
    chain_document = chain.sealed_document(
        include_reference=lambda row: not (
            row["scope"] == "output" and row["ref"].startswith(release_prefix)
        )
    )
    return (
        {
            "scope": "output",
            "ref": f"data/tasks/{execution_id}/_shared/receipts/009-release.json",
            "digest": _digest(chain.terminal_raw),
        },
        chain_document,
    )


def _validate_embedded_execution_chain(
    *,
    chain_document: Mapping[str, Any],
    cohort_binding: Mapping[str, Any],
    cohort_raw: bytes,
    release_id: str,
    release_root: Path,
    header_ref: str,
    header_digest: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    header_raw = _assert_no_symlink(
        release_root / release_id / "payload/release.json",
        label="sealed release header",
    ).read_bytes()
    external = {
        ("output", str(cohort_binding["ref"]), str(cohort_binding["digest"])): cohort_raw,
        ("output", header_ref, header_digest): header_raw,
    }
    for binding in _chain_bindings(chain_document):
        raw = _sealed_release_ref_bytes(
            binding=binding, release_id=release_id, release_root=release_root
        )
        if raw is not None:
            key = (
                str(binding.get("scope")),
                str(binding.get("ref")),
                str(binding.get("digest")),
            )
            external[key] = raw
    try:
        chain = validate_embedded_receipt_chain(
            chain_document,
            external_bytes=external,
            expected_count=9,
            terminal_verdict="pass",
        )
    except ReceiptChainError as exc:
        raise _error("DATA.RELEASE.HANDOFF_EXECUTION_CHAIN_INVALID", str(exc)) from exc
    execution_id = chain.execution_id
    release_open = chain.open_requests[-1]
    terminal = chain.terminal_receipt
    if {"scope": "output", "ref": cohort_binding["ref"], "digest": cohort_binding["digest"]} not in release_open.get("inputRefs", []):
        raise _error("DATA.RELEASE.HANDOFF_COHORT_OPEN_UNBOUND", execution_id)
    if {"scope": "output", "ref": header_ref, "digest": header_digest} not in terminal.get("resultRefs", []):
        raise _error("DATA.RELEASE.HANDOFF_RECEIPT_RELEASE_UNBOUND", execution_id)
    return (
        {
            "scope": "output",
            "ref": f"data/tasks/{execution_id}/_shared/receipts/009-release.json",
            "digest": _digest(chain.terminal_raw),
        },
        chain.terminal_receipt,
    )


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
        try:
            expected_bindings = [
                binding.as_document()
                for binding in project_content_library_bindings(raw_bindings)
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
    try:
        assert_valid(value, "release", "producer_release_handoff", label="producer release handoff")
    except (TypeError, ValueError) as exc:
        raise _error("DATA.RELEASE.HANDOFF_SCHEMA_INVALID", str(exc)) from exc
    if not isinstance(value, Mapping):
        raise _error("DATA.RELEASE.HANDOFF_SCHEMA_INVALID", "document must be object")
    document = dict(value)
    execution_ids = document["executionIds"]
    if execution_ids != sorted(execution_ids) or len(execution_ids) != len(set(execution_ids)):
        raise _error("DATA.RELEASE.HANDOFF_EXECUTIONS_INVALID", "executionIds must be sorted unique")
    revision = str(document["producerBaselineRevision"])
    if not _COMMIT.fullmatch(revision):
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_INVALID", revision)
    cohort_binding = document["explicitCohort"]
    cohort = cohort_binding.get("document") if isinstance(cohort_binding, Mapping) else None
    if not isinstance(cohort, Mapping):
        raise _error("DATA.RELEASE.COHORT_INVALID", "embedded document missing")
    cohort = dict(cohort)
    cohort_raw = _canonical_bytes(cohort)
    try:
        assert_valid(cohort, "release", "release_cohort", label="explicit cohort")
    except ValueError as exc:
        raise _error("DATA.RELEASE.COHORT_INVALID", str(exc)) from exc
    if cohort_binding.get("digest") != _digest(cohort_raw):
        raise _error("DATA.RELEASE.HANDOFF_DIGEST_DRIFT", "explicit cohort")
    if cohort.get("producerBaselineRevision") != revision:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_DRIFT", revision)
    release_id = str(document["releaseId"]); milestone = str(document["milestone"])
    header, counts, header_digest, release_digest = _validate_release_facts(release_id=release_id, release_root=release_root, cohort=cohort, milestone=milestone)
    if header.get("executionIds") != execution_ids:
        raise _error("DATA.RELEASE.HANDOFF_EXECUTIONS_INVALID", "release header executionIds drift")
    header_ref = f"data/releases/{release_id}/payload/release.json"
    expected_release = {"scope":"output","ref":f"data/releases/{release_id}","payloadDigest":release_digest,"headerRef":header_ref,"headerDigest":header_digest}
    if document["release"] != expected_release:
        raise _error("DATA.RELEASE.HANDOFF_RELEASE_DIGEST_DRIFT", release_id)
    chain_documents = document["receiptChains"]
    frozen_references = document["frozenReferences"]
    if (
        not isinstance(chain_documents, list)
        or [row.get("executionId") for row in chain_documents if isinstance(row, Mapping)]
        != execution_ids
        or not isinstance(frozen_references, list)
        or any(not isinstance(row, Mapping) for row in frozen_references)
    ):
        raise _error("DATA.RELEASE.HANDOFF_EXECUTIONS_INVALID", "receiptChains/bundle shape")
    frozen_by_key = {
        _frozen_reference_key(row): dict(row) for row in frozen_references
    }
    if len(frozen_by_key) != len(frozen_references):
        raise _error("DATA.RELEASE.HANDOFF_EXECUTION_CHAIN_INVALID", "duplicate frozen bundle ref")
    used_frozen_keys: set[tuple[str, str, str]] = set()
    expected_receipts = []
    for execution_id, chain_document in zip(execution_ids, chain_documents, strict=True):
        if not isinstance(chain_document, Mapping):
            raise _error("DATA.RELEASE.HANDOFF_EXECUTION_CHAIN_INVALID", execution_id)
        chain_binding_keys = {
            _frozen_reference_key(binding)
            for binding in _chain_bindings(chain_document)
        }
        chain_frozen_keys = chain_binding_keys & set(frozen_by_key)
        used_frozen_keys.update(chain_frozen_keys)
        sealed_chain = {
            **dict(chain_document),
            "frozenReferences": [
                frozen_by_key[key] for key in sorted(chain_frozen_keys)
            ],
        }
        binding, _ = _validate_embedded_execution_chain(
            chain_document=sealed_chain,
            cohort_binding=cohort_binding,
            cohort_raw=cohort_raw,
            release_id=release_id,
            release_root=release_root,
            header_ref=header_ref,
            header_digest=header_digest,
        )
        expected_receipts.append({"executionId": execution_id, "receipt": binding})
    if used_frozen_keys != set(frozen_by_key):
        raise _error(
            "DATA.RELEASE.HANDOFF_EXECUTION_CHAIN_INVALID",
            "frozen bundle contains unused or missing exact bytes",
        )
    if document["producerReleaseReceipts"] != expected_receipts:
        raise _error("DATA.RELEASE.HANDOFF_RECEIPTS_INVALID", release_id)
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
    """Revalidate a handoff using only sealed release bytes plus handoff."""
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
    revision = str(producer_baseline_revision)
    if not _COMMIT.fullmatch(revision):
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_INVALID", revision)
    if cohort.get("producerBaselineRevision") != revision:
        raise _error("DATA.RELEASE.HANDOFF_BASELINE_DRIFT", revision)
    external_cohort_binding = _binding_for_path(cohort_path, repo_root=repo_root, output_root=output_root, label="explicit cohort")
    cohort_binding = {**external_cohort_binding, "document": cohort}
    target = release_root / release_id / _FILE_NAME
    if target.exists():
        try:
            existing_document, _ = _read_json_file(
                target, label="producer handoff", canonical=True
            )
            _validate_handoff(
                existing_document,
                repo_root=repo_root,
                output_root=output_root,
                release_root=release_root,
            )
        except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
            raise _error(
                "DATA.RELEASE.HANDOFF_CREATE_ONCE_CONFLICT", str(target)
            ) from exc
        if (
            existing_document.get("releaseId") != release_id
            or existing_document.get("milestone") != milestone
            or existing_document.get("producerBaselineRevision") != revision
            or existing_document.get("explicitCohort") != cohort_binding
        ):
            raise _error("DATA.RELEASE.HANDOFF_CREATE_ONCE_CONFLICT", str(target))
        return existing_document, target, True

    revision = _validate_producer_baseline_revision(revision, repo_root=repo_root)
    policy_targets = load_content_distribution_policy().milestone_targets().get(milestone)
    if policy_targets is None:
        raise _error("DATA.RELEASE.COHORT_MILESTONE_INVALID", milestone)
    header, counts, header_digest, release_digest = _validate_release_facts(
        release_id=release_id,
        release_root=release_root,
        cohort=cohort,
        milestone=milestone,
        policy_targets=policy_targets,
    )
    execution_ids = header.get("executionIds")
    if not isinstance(execution_ids, list) or not execution_ids or execution_ids != sorted(execution_ids) or len(execution_ids) != len(set(execution_ids)):
        raise _error("DATA.RELEASE.HANDOFF_EXECUTIONS_INVALID", "release header executionIds must be complete sorted unique")
    header_ref = f"data/releases/{release_id}/payload/release.json"
    receipts = []
    receipt_chains = []
    frozen_bundle: dict[tuple[str, str, str], dict[str, str]] = {}
    for execution_id in execution_ids:
        binding, chain_document = _validate_live_execution_chain(
            execution_id=execution_id,
            execution_root=output_root / "data/tasks" / execution_id,
            repo_root=repo_root,
            output_root=output_root,
            cohort_binding=external_cohort_binding,
            header_ref=header_ref,
            header_digest=header_digest,
            release_id=release_id,
        )
        receipts.append({"executionId": execution_id, "receipt": binding})
        for row in chain_document.pop("frozenReferences"):
            key = _frozen_reference_key(row)
            existing = frozen_bundle.get(key)
            if existing is not None and existing != row:
                raise _error(
                    "DATA.RELEASE.HANDOFF_EXECUTION_CHAIN_INVALID",
                    f"frozen ref collision: {key[0]}:{key[1]}",
                )
            frozen_bundle[key] = row
        receipt_chains.append(chain_document)
    base_document = {
        "schema": _SCHEMA, "handoffId": release_id, "releaseId": release_id,
        "executionIds": execution_ids, "milestone": milestone, "carrierCounts": counts,
        "release": {"scope":"output","ref":f"data/releases/{release_id}","payloadDigest":release_digest,"headerRef":header_ref,"headerDigest":header_digest},
        "producerReleaseReceipts": receipts, "explicitCohort": cohort_binding,
        "receiptChains": receipt_chains,
        "frozenReferences": [frozen_bundle[key] for key in sorted(frozen_bundle)],
        "producerBaselineRevision": revision,
    }

    _validate_current_producer_contract_baseline(revision, repo_root=repo_root)
    pool_rows = _project_live_pool_rows(
        live_root=publish_root,
        sealed_root=release_root / release_id / "payload/objects",
        object_refs=list(cohort["objectRefs"]),
        header=header,
        release_class=str(cohort.get("releaseClass") or ""),
    )
    document = {**base_document, "contentPoolObjects": pool_rows}
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
            _validate_handoff(
                document, repo_root=repo_root, output_root=output_root,
                release_root=release_root
            )
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


__all__ = ["ProducerReleaseHandoffError", "read_producer_release_handoff", "validate_producer_release_handoff", "write_producer_release_handoff"]
