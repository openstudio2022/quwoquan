"""Derive the immutable repository-input digest for data executions and releases.

The digest is evidence, not a second source of truth. It names only fixed
repository input roots and hashes their files in a deterministic order, so deleting
``.qwq_output`` never removes configuration required to rebuild an execution.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

from core.paths import DATA_CACHE_ROOT, REPO_ROOT

_SOURCE_DEFINITION_INPUT_ROOTS = (
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
_EXECUTION_BUNDLE_INPUT_ROOTS = (
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
)
# Historical combined sourceDigest documents used the broad scripts root. Keep
# that input name only for immutable terminal evidence parsing; current producer
# source-definition and execution-bundle identities use the exact tuples above.
_LEGACY_SOURCE_DIGEST_INPUT_ROOTS = (
    "quwoquan_data/scripts",
    *_SOURCE_DEFINITION_INPUT_ROOTS,
)
# Data execution identity is deliberately environment-neutral. Environment
# topology and readiness policy apply only when an immutable release is shipped.
_DIGEST_PREFIX = "sha256:"
_EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store", ".gitkeep"}
_CACHE_VERSION = 1


class SourceDigestError(ValueError):
    """The repository inputs cannot be represented by the fixed digest contract."""


@dataclass(frozen=True, slots=True)
class SourceDigest:
    """A compact, reproducible fingerprint of the data production inputs."""

    digest: str

    @classmethod
    def build(
        cls,
        *,
        repo_root: Path = REPO_ROOT,
        cache_path: Path | None = None,
    ) -> SourceDigest:
        normalized_root = repo_root.expanduser().resolve()
        selected_cache = (
            cache_path
            if cache_path is not None
            else _default_cache_path(normalized_root)
        )
        cache_guard = (
            _cache_lock(selected_cache)
            if selected_cache is not None
            else nullcontext()
        )
        with cache_guard:
            cache = (
                _load_cache(selected_cache)
                if selected_cache is not None
                else {"version": _CACHE_VERSION, "entries": {}}
            )
            previous_entries = cache.get("entries")
            if not isinstance(previous_entries, Mapping):
                previous_entries = {}
            next_entries: dict[str, dict[str, object]] = {}
            digest = hashlib.sha256()
            for relative_root in _LEGACY_SOURCE_DIGEST_INPUT_ROOTS:
                root = normalized_root / relative_root
                if not root.exists():
                    raise SourceDigestError(
                        f"source digest input is missing: {relative_root}"
                    )
                for path in _iter_files(root):
                    relative = path.relative_to(normalized_root).as_posix()
                    stat = path.stat()
                    identity = {
                        "size": int(stat.st_size),
                        "mtimeNs": int(stat.st_mtime_ns),
                        "ctimeNs": int(stat.st_ctime_ns),
                        "device": int(stat.st_dev),
                        "inode": int(stat.st_ino),
                    }
                    cached = previous_entries.get(relative)
                    file_digest = ""
                    if isinstance(cached, Mapping) and all(
                        cached.get(key) == value for key, value in identity.items()
                    ):
                        candidate = cached.get("sha256")
                        if isinstance(candidate, str) and _is_raw_sha256(candidate):
                            file_digest = candidate
                    if not file_digest:
                        file_digest = _file_sha256(path)
                    next_entries[relative] = {**identity, "sha256": file_digest}
                    digest.update(relative.encode("utf-8"))
                    digest.update(b"\0")
                    digest.update(file_digest.encode("ascii"))
                    digest.update(b"\n")
            if selected_cache is not None:
                _write_cache(
                    selected_cache,
                    {"version": _CACHE_VERSION, "entries": next_entries},
                )
        return cls(digest=_DIGEST_PREFIX + digest.hexdigest())

    @classmethod
    def from_document(cls, value: object) -> SourceDigest:
        if not isinstance(value, Mapping):
            raise SourceDigestError("sourceDigest must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("sourceDigest fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("sourceDigest.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError("sourceDigest.digest must be a sha256 digest")
        inputs = value.get("inputs")
        if not isinstance(inputs, list) or tuple(inputs) != _LEGACY_SOURCE_DIGEST_INPUT_ROOTS:
            raise SourceDigestError("sourceDigest.inputs must name the fixed repository inputs")
        return cls(digest=digest)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(_LEGACY_SOURCE_DIGEST_INPUT_ROOTS),
        }


@dataclass(frozen=True, slots=True)
class ExecutionBundleIdentity:
    """Immutable identity of the code/policy bundle that executes a snapshot."""

    digest: str

    @classmethod
    def build(cls, *, repo_root: Path = REPO_ROOT) -> ExecutionBundleIdentity:
        return cls(
            digest=_digest_roots(
                repo_root.expanduser().resolve(),
                _EXECUTION_BUNDLE_INPUT_ROOTS,
            )
        )

    @classmethod
    def from_document(cls, value: object) -> ExecutionBundleIdentity:
        if not isinstance(value, Mapping):
            raise SourceDigestError("executionBundle must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("executionBundle fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("executionBundle.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError("executionBundle.digest must be a sha256 digest")
        if tuple(value.get("inputs") or ()) != _EXECUTION_BUNDLE_INPUT_ROOTS:
            raise SourceDigestError(
                "executionBundle.inputs must name the fixed execution inputs"
            )
        return cls(digest=digest)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(_EXECUTION_BUNDLE_INPUT_ROOTS),
        }


@dataclass(frozen=True, slots=True)
class SourceDefinitionSnapshot:
    """Content-semantic and physical-source definitions frozen for a candidate."""

    digest: str

    @classmethod
    def build(cls, *, repo_root: Path = REPO_ROOT) -> SourceDefinitionSnapshot:
        return cls(
            digest=_digest_roots(
                repo_root.expanduser().resolve(),
                _SOURCE_DEFINITION_INPUT_ROOTS,
            )
        )

    @classmethod
    def from_document(cls, value: object) -> SourceDefinitionSnapshot:
        if not isinstance(value, Mapping):
            raise SourceDigestError("sourceDigest must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("sourceDigest fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("sourceDigest.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError("sourceDigest.digest must be a sha256 digest")
        if tuple(value.get("inputs") or ()) != _SOURCE_DEFINITION_INPUT_ROOTS:
            raise SourceDigestError(
                "sourceDigest.inputs must name the fixed source-definition inputs"
            )
        return cls(digest=digest)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(_SOURCE_DEFINITION_INPUT_ROOTS),
        }


@dataclass(frozen=True, slots=True)
class FrozenSourceDigest:
    """A validated historical input closure bound to pre-snapshot object evidence."""

    digest: str
    inputs: tuple[str, ...]

    @classmethod
    def from_document(cls, value: object) -> FrozenSourceDigest:
        if not isinstance(value, Mapping):
            raise SourceDigestError("frozen sourceDigest must be an object")
        if set(value) != {"algorithm", "digest", "inputs"}:
            raise SourceDigestError("frozen sourceDigest fields are invalid")
        if value.get("algorithm") != "sha256":
            raise SourceDigestError("frozen sourceDigest.algorithm must be sha256")
        digest = value.get("digest")
        if not isinstance(digest, str) or not _is_sha256(digest):
            raise SourceDigestError(
                "frozen sourceDigest.digest must be a sha256 digest"
            )
        raw_inputs = value.get("inputs")
        if not isinstance(raw_inputs, list) or not raw_inputs:
            raise SourceDigestError("frozen sourceDigest.inputs must not be empty")
        inputs = tuple(str(item or "").strip() for item in raw_inputs)
        if (
            any(
                not item
                or item.startswith("/")
                or any(part in {".", ".."} for part in item.split("/"))
                for item in inputs
            )
            or len(inputs) != len(set(inputs))
        ):
            raise SourceDigestError("frozen sourceDigest.inputs are invalid")
        return cls(digest=digest, inputs=inputs)

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": "sha256",
            "digest": self.digest,
            "inputs": list(self.inputs),
        }


def parse_source_digest_document(value: object) -> SourceDigest:
    """Parse the current input truth for one source digest document."""
    return SourceDigest.from_document(value)


def parse_immutable_source_digest_document(
    value: object,
) -> SourceDigest | SourceDefinitionSnapshot:
    """Parse either immutable identity generation from frozen release evidence.

    Frozen evidence cannot be migrated, so both generations must stay readable:
    current producers bind the source-definition identity on its own, while
    terminal historical evidence still carries the retired combined closure.
    The generation is decided by the named inputs, never by a version field.
    """

    raw_inputs = value.get("inputs") if isinstance(value, Mapping) else None
    if (
        isinstance(raw_inputs, list)
        and tuple(raw_inputs) == _SOURCE_DEFINITION_INPUT_ROOTS
    ):
        return SourceDefinitionSnapshot.from_document(value)
    return SourceDigest.from_document(value)


def current_source_digest(*, repo_root: Path = REPO_ROOT) -> SourceDigest:
    """Return the only source digest used by execution and release evidence."""
    return SourceDigest.build(repo_root=repo_root)


def current_source_definition_snapshot(
    *, repo_root: Path = REPO_ROOT
) -> SourceDefinitionSnapshot:
    return SourceDefinitionSnapshot.build(repo_root=repo_root)


def current_execution_bundle_identity(
    *, repo_root: Path = REPO_ROOT
) -> ExecutionBundleIdentity:
    return ExecutionBundleIdentity.build(repo_root=repo_root)


def content_source_revision(
    *,
    source_digest: str,
    entity_catalog_digest: str,
) -> str:
    """Derive the content revision shared by task and release evidence."""
    if not _is_sha256(source_digest):
        raise SourceDigestError("sourceDigest must be a sha256 digest")
    if not _is_sha256(entity_catalog_digest):
        raise SourceDigestError("entityCatalogDigest must be a sha256 digest")
    encoded = json.dumps(
        {
            "schema": "quwoquan_data.content_source_revision",
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_catalog_digest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def _iter_files(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not any(part in _EXCLUDED_PARTS for part in path.parts)
    )


def _digest_roots(repo_root: Path, roots: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative_root in roots:
        root = repo_root / relative_root
        if not root.exists():
            raise SourceDigestError(
                f"source identity input is missing: {relative_root}"
            )
        for path in _iter_files(root):
            relative = path.relative_to(repo_root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(_file_sha256(path).encode("ascii"))
            digest.update(b"\n")
    return _DIGEST_PREFIX + digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_cache_path(repo_root: Path) -> Path | None:
    if repo_root == REPO_ROOT.resolve():
        return DATA_CACHE_ROOT / "source-digest" / "file-hashes-v1.json"
    # A source capsule/snapshot is deliberately not a Git worktree and may be
    # read-only.  Persistent caching is an optimization for normal repositories,
    # never part of the immutable source identity or capsule tree.
    if not (repo_root / ".git").exists():
        return None
    return (
        repo_root
        / ".qwq_output"
        / "data"
        / "local"
        / "cache"
        / "source-digest"
        / "file-hashes-v1.json"
    )


def _load_cache(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": _CACHE_VERSION, "entries": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"version": _CACHE_VERSION, "entries": {}}
    if not isinstance(value, dict) or value.get("version") != _CACHE_VERSION:
        return {"version": _CACHE_VERSION, "entries": {}}
    return value


def _write_cache(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _cache_lock(cache_path: Path) -> Iterator[None]:
    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_raw_sha256(value: str) -> bool:
    return len(value) == hashlib.sha256().digest_size * 2 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_sha256(value: str) -> bool:
    if not value.startswith(_DIGEST_PREFIX):
        return False
    raw = value.removeprefix(_DIGEST_PREFIX)
    return _is_raw_sha256(raw)


__all__ = [
    "ExecutionBundleIdentity",
    "FrozenSourceDigest",
    "SourceDigest",
    "SourceDefinitionSnapshot",
    "SourceDigestError",
    "content_source_revision",
    "current_execution_bundle_identity",
    "current_source_definition_snapshot",
    "current_source_digest",
    "parse_immutable_source_digest_document",
    "parse_source_digest_document",
]
