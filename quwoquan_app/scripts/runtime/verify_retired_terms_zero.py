#!/usr/bin/env python3
"""Fail when retired terminology appears in repository text files."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SKIP_DIRS = {
    ".git",
    ".dart_tool",
    "build",
    "node_modules",
    ".idea",
    ".vscode",
    ".venv",
    # 本地测试 Python 虚拟环境（PIL/pytest/numpy 等第三方包），非本仓库源码，不参与用语门禁。
    ".qwq_test_venv",
    "site-packages",
    # 本地可选克隆的 Cursor 侧向仓库；锁文件等含第三方用语，不参与本仓库用语门禁。
    "cursor-cookbook",
}

TEXT_SUFFIXES = {
    ".arb",
    ".dart",
    ".go",
    ".gradle",
    ".json",
    ".jsonl",
    ".lock",
    ".md",
    ".mdc",
    ".mjs",
    ".properties",
    ".py",
    ".rb",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_NAMES = {
    "Makefile",
    "Podfile",
}

TERMS = (
    "".join(("leg", "acy")),
    "".join(("Leg", "acy")),
    "".join(("LEG", "ACY")),
    chr(0x9057) + chr(0x7559),
    chr(0x65E7) + chr(0x7248),
    chr(0x5386) + chr(0x53F2),
)

ALLOWLIST_PREFIXES = {
    "quwoquan_app/test/ui/content/markdown/fixtures/",
    "quwoquan_data/runtime/",
    "quwoquan_data/publish/",
    "quwoquan_data/sop/",
    "quwoquan_data/docs/",
    "quwoquan_data/data/",
    "quwoquan_data/schema/produce/templates/",
    # 数据工程领域内容/模板（文旅实体的过往脉络与背景等核心领域文案）。
    "quwoquan_data/templates/",
    # 数据工程脚本（pre-schema 残留 posts 透明审计、既往脚本薄壳化收敛等技术语义）。
    "quwoquan_data/scripts/",
    # 变更日志为只追加的过往记录，天然描述既往清理过程。
    "specs/changelog/",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/",
}

ALLOWLIST_PATHS = {
    "deploy/shared/media_slice_registry.json",
    "deploy/shared/process_domain_mapping_runbook.md",
    "quwoquan_app/lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart",
    "quwoquan_service/contracts/metadata/messages/conversation/fields.yaml",
    "quwoquan_service/contracts/metadata/messages/conversation/service.yaml",
    "quwoquan_service/runtime/media/slice_object_key.go",
    "quwoquan_service/runtime/media/slice_object_key_test.go",
    "quwoquan_service/services/chat-service/internal/application/conversation_kind.go",
    "quwoquan_service/services/chat-service/internal/application/group_avatar_support_test.go",
    "quwoquan_service/services/user-service/tests/auth_contract_test.go",
    "quwoquan_service/services/user-service/tests/helpers_test.go",
    "quwoquan_service/services/user-service/tests/invite_contract_test.go",
    "quwoquan_service/services/user-service/tests/sub_account_view_contract_test.go",
    "quwoquan_service/specs/runtime/media/04-object-key-and-url-spec.md",
    "quwoquan_service/scripts/media/media_slice_registry.py",
    "quwoquan_service/scripts/seed/shared_pool_real_asset_pipeline.py",
    "agent_ops/avatar/verify_avatar_user_pool_consistency.py",
    "agent_ops/ci/verify_ci_profile_consistency.py",
    "quwoquan_service/scripts/gamma/verify_gamma_validation_profiles.py",
    "quwoquan_data/tools/catalog_iteration.py",
    "quwoquan_data/tools/semantic_entity_resolution.py",
    ".cursor/commands/data-explore.md",
    ".cursor/commands/infra-plan.md",
    ".cursor/rules/13-coding-discipline.mdc",
    "quwoquan_app/lib/cloud/services/tag/mock/tag_mock_data.dart",
    "quwoquan_data/README.md",
    "quwoquan_data/schema/tag/tag_policy.yaml",
    "quwoquan_data/scripts/bootstrap_admin_regions.py",
    "quwoquan_data/scripts/bootstrap_school_entities.py",
    "quwoquan_data/scripts/bootstrap_sop.py",
    "quwoquan_data/scripts/bootstrap_tags.py",
    "quwoquan_data/scripts/e2e_smoke_v4.py",
    "quwoquan_data/scripts/sample_data/build_all.py",
    "quwoquan_data/scripts/tag_alias_migrate.py",
    "quwoquan_data/scripts/verify_tag_tree.py",
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/design.md",
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md",
    # 门禁脚本：职责即检测/禁止退役项，故自身含被检词。
    "agent_ops/gate/verify_prod_rollout_stackctl_contract.py",
    "quwoquan_app/scripts/runtime/verify_file_line_budget.py",
    "quwoquan_app/scripts/runtime/verify_repository_interface_method_budget.py",
    "quwoquan_service/scripts/contract/verify_tag_ref_source_of_truth.py",
    "specs/gates/file_line_budget_allowlist.yaml",
    "specs/gates/repository_interface_method_budget_allowlist.yaml",
    # 端侧技术注释：过往数据回退/过往归属键，非用户可见退役术语。
    "quwoquan_app/lib/assistant/session/assistant_session_store.dart",
    "quwoquan_app/lib/ui/assistant/providers/personal_assistant_stream_controller.dart",
    # profile_shell 注释记录早先 resonance 假数据已删；测试断言陈旧 blocks 被排除/避免残留 Timer。
    "quwoquan_app/lib/ui/user/widgets/profile_shell.dart",
    "quwoquan_app/test/ui/content/entry/publish_draft_projection_bridge_test.dart",
    "quwoquan_app/test/ui/discovery/home_page_widget_test.dart",
    # 规格/设计/验收/报告：描述 V5/V6 既往口径差异与残留清理裁决，属元文档。
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/tag-service-intersection-readiness.md",
    "specs/feature-tree/runtime/native-edge-gesture-navigation/design.md",
    "specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/design.md",
    "specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/profile-commercial-readiness/acceptance.yaml",
    "specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md",
    "specs/gates/v6_git_branch_cleanup_decisions.md",
    "specs/gates/v6_intersection_closure_acceptance_report.md",
}


def is_scannable(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.is_file() and (
        path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES
    )


def is_allowlisted(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel in ALLOWLIST_PATHS:
        return True
    return any(rel.startswith(prefix) for prefix in ALLOWLIST_PREFIXES)


def main() -> int:
    violations: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not is_scannable(path):
            continue
        if is_allowlisted(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lower = text.lower()
        if any(term.lower() in lower for term in TERMS):
            violations.append(path.relative_to(ROOT).as_posix())

    if violations:
        print("verify_retired_terms_zero: FAIL")
        for rel in violations:
            print(f"  - {rel}")
        return 1
    print("verify_retired_terms_zero: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
