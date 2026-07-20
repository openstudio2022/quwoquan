#!/usr/bin/env python3
"""生成全仓目录整洁审计报告。

该命令只读取 Git 与工作树，不删除、不修改源码。报告写入统一的
``.qwq_output/env/repo/runs``，用于在清理前冻结当前脏工作树和候选证据。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import repo_run_dir

HIGH_CONFIDENCE_PATHS = {
    ".gitmodules": "App 已是 monorepo 普通目录，残留 submodule 声明与 Git 索引不一致",
    "quwoquan_service/api": "服务端默认 go build Mach-O 输出，源码树不应保存构建产物",
    "quwoquan_service/services/user-service/internal/infrastructure/user/persistence/pg__store.g.go": "缺少实体映射时生成的非法空名 PG store，metadata 与 codegen 已改为 fail-fast",
    "quwoquan_service/services/user-service/internal/domain/user/model/.g.go": "无实体辅助表生成的非法空名 Go model，metadata 已标记 infrastructure_only",
    "quwoquan_service/api_integration.test": "已跟踪的服务端 Mach-O 测试二进制，源码树不应保存构建产物",
    "quwoquan_app/scripts/content/verify_content_post_mock_test_roots.py": "校验已不存在的旧 test/ui 与 test/cloud 根目录，且无活动入口引用",
    "quwoquan_app/docs/content_post_mock_test_alignment.md": "只说明已退役的旧 mock-test 根目录校验脚本",
    "quwoquan_app/scripts/chat/regenerate_conv_grid_group_avatars.py": "生成入口与目标 fixture 均已不存在，且无活动调用方",
    "quwoquan_app/assets/assistant/config/agent_run_observability_schema.json": "无运行时、测试、生成器或 metadata 消费者的打包孤儿配置",
    "quwoquan_app/assets/assistant/config/geo_resolution_config.json": "无运行时、测试、生成器或 metadata 消费者的打包孤儿配置",
    "quwoquan_app/assets/assistant/config/retrieval_time_contract.json": "无运行时、测试、生成器或 metadata 消费者的打包孤儿配置",
    "quwoquan_app/assets/assistant/config/user_phase_hints.json": "无运行时、测试、生成器或 metadata 消费者的打包孤儿配置",
    "quwoquan_app/scripts/runtime/.verify_dart_semantic_baseline.txt": "语义债务已清零，门禁已改为零容忍且不再允许更新历史基线",
    "quwoquan_app/scripts/runtime/.verify_error_code_semantic_baseline.txt": "错误码语义债务已清零，门禁已改为零容忍且不再允许更新历史基线",
    "quwoquan_app/scripts/runtime/.verify_unified_error_semantics_ratchet_baseline.txt": "统一错误语义债务已清零，门禁已改为零容忍且不再允许更新历史基线",
    "quwoquan_app/scripts/media/render_group_avatar_composite.swift": "无调用方的 macOS 专用头像渲染器，已由 canonical Go 工具取代",
    "quwoquan_app/scripts/verify_orchestration_map_governance.py": "目标目录已不存在且会空扫假绿的孤立门禁",
    "quwoquan_app/scripts/run_ios_simulator.sh": "仅剩历史 CR 引用的第二套 iOS 启动入口",
    "quwoquan_app/scripts/content/run_l2_content_tests.sh": "退役的 L2 命名与裸本地 Mongo 测试入口，统一由 api_integration gate 承接",
    "quwoquan_app/scripts/ios/test_ios_shortcut_log_hygiene.py": "测试已迁入 local_contract 测试树",
    "quwoquan_app/vendor/plugins/video_thumbnail/grep": "零字节 vendor 残片，无构建或源码引用",
    "quwoquan_data/scripts/verify/audit/__init__.py": "未注册的旧 Data audit 包，唯一 release-integrity 入口已迁入 verify handler",
    "quwoquan_data/scripts/verify/audit/handler.py": "未注册且与 verify release-integrity 重复的旧 Data audit handler",
    "quwoquan_ops/cli/gamma/check_public_ip_open_port.py": "远端 gamma 已退役，本地公网回源端口探针无活动入口",
    "quwoquan_ops/cli/gamma/start_gamma_local_media_origin.sh": "远端 gamma 已退役，媒体公网回源旁路不再属于当前拓扑",
    "quwoquan_ops/cli/gamma/start_public_ip_media_origin.sh": "远端 gamma 已退役，公网媒体回源包装脚本无活动入口",
    "quwoquan_ops/cli/gamma/verify_gamma_environment_ready.py": "无活动入口的旧 gamma readiness 包装器",
    "quwoquan_ops/cli/gamma/verify_gamma_public_gateway_routing.py": "无活动入口且带写请求副作用的旧 gamma readiness 探针",
    "quwoquan_ops/cli/gamma/run_gamma_patrol_matrix_ci.py": "已被通用环境 Patrol runner 取代的旧 gamma 专用矩阵",
    "quwoquan_ops/cli/beta/verify_ops_control_plane_smoke.sh": "无调用方且硬编码退役端口的旧 beta smoke",
    "quwoquan_ops/gate/verify_artifacts_layout.py": "无调用方且只转发 root layout 的兼容门禁",
    "quwoquan_ops/gate/scaffold/migrate_acceptance_test_evidence.py": "迁移已完成的一次性 acceptance 迁移器",
    "quwoquan_service/scripts/install-hooks.sh": "已迁移到 Ops scaffold 的兼容转发壳",
    "quwoquan_service/scripts/media/verify_gamma_curated_media_routes.py": "无调用方且已由 stackctl 媒体探针取代",
    "quwoquan_service/scripts/media/media_slice_server.py": "只与旧 registry 互相引用的媒体切片孤岛",
    "quwoquan_service/scripts/media/media_slice_registry.py": "只与旧 server 互相引用的媒体切片孤岛",
    "quwoquan_service/scripts/content/run_content_import_mongo_test.sh": "未启用 mongo_integration build tag、实际不执行目标测试的孤立 runner",
    "quwoquan_service/scripts/verify/verify_redis_keyspace.py": "未登记前缀分支直接 pass 的假绿门禁，已由 Redis router codegen --check 取代",
    "quwoquan_service/scripts/recommendation/eval_interest_profile.py": "无规格、测试或调用方的旧单点评估脚本，闭环评估由 eval_content_flywheel_loop 承接",
    "quwoquan_service/scripts/search/verify_search_service_module.sh": "根 Go module 构建与测试已由统一 service gate 承接的重复包装器",
    "quwoquan_service/scripts/search/test_output_paths.py": "测试已迁入 Ops local_contract 测试树",
    "quwoquan_service/services/assistant-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/content-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/entity-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/integration-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/platform-ops-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/product-ops-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/search-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/tag-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "quwoquan_service/services/user-service/configs/config.yaml": "已由 default + environment 配置单轨取代",
    "specs/feature-tree/runtime/runtime-media/gamma-local-origin-runbook.md": "描述已退役的 ECS gamma 公网回源旁路",
    "specs/feature-tree/discovery-content/content-type-framework/content-unification-admission-gate-checklist.md": "已完成的历史执行清单，不属于特性树正式 spec/design/acceptance 文档",
    "quwoquan_ops/environments/workflow_consolidation_plan.md": "已被 CI/CD 端到端设计取代，且仍描述不存在的远端 gamma workflows",
    "specs/changelog/CR-20260330-010-mock-isolation-implementation-wave.md": "非规范 Markdown CR 副本，且声明的 YAML 真相源从未存在",
    "specs/feature-tree/02_JOURNEY_SCENARIO_MIGRATION_GUIDE.md": "描述已废止的树内计划文档迁移模型",
    "specs/feature-tree/03_PROFILE_HOMEPAGE_REDESIGN_MIGRATION_SAMPLE.md": "已完成的迁移样板，仍以废止的树内计划文档为目标",
    "specs/feature-tree/recommendation-platform/preconditions.md": "Create 阶段历史清单，重复 spec/acceptance 且引用已废止 tasks",
    "specs/feature-tree/recommendation-platform/rec-model-service/readiness.md": "历史就绪清单，重复 L3 spec/acceptance 且包含旧接口口径",
    "specs/feature-tree/runtime/runtime-recommendation/推荐系统八期审计规划.plan.md": "历史会话计划文件，不属于正式特性树文档",
    "specs/feature-tree/runtime/tree.yaml": "已退役的第二套特性树镜像，canonical tree_index 已完整承接",
    "specs/feature-tree/assistant-run-learning/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/chat-conversation/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/circle-community/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/discovery-content/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/gateway-orchestrator-foundation/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/global-search-experience/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/platform-ops-governance/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/product-ops-growth/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/user-identity-profile-relationship/tree.yaml": "已退役的旧五层特性树镜像",
    "specs/feature-tree/experience_coverage_standard.md": "无消费者的旧体验覆盖说明，正式验收已由特性树 acceptance 承接",
    "specs/feature-tree/runtime/runtime-messaging/reliable-async-task-channel/self_check.md": "已完成的历史自检清单，不属于正式特性树文档",
    "specs/feature-tree/runtime/runtime-client-foundation/user_domain_dynamic_audit.md": "无消费者的历史审计快照",
    "specs/feature-tree/runtime/runtime-client-foundation/map-typing-m4-chat-user-rtc-status.md": "无消费者的历史状态快照",
    "docs/intersection-unification-plan.md": "无消费者的旧执行计划，当前规格已进入 canonical feature tree",
    "docs/exception-observability-rollout.md": "无消费者且保留已退役 mock/remote 双轨的历史 rollout 文档",
    "docs/user_facing_prompt_backlog.md": "已解决的第二套 backlog，长期风险只允许进入正式风险清单",
    "specs/gates/environment_noise_cleanup_inventory.md": "已完成且无消费者的历史清理 inventory",
    "specs/gates/phase2_acceptance.md": "无消费者的旧 phase 验收凭证，不属于当前三层测试模型",
    "specs/gates/phase3_acceptance.md": "无消费者的旧 phase 验收凭证，不属于当前三层测试模型",
    "specs/gates/notification_service_seed_gap.md": "与当前已落地 notification-service 冲突的历史缺口说明",
    "specs/gates/session_b_current_governance.md": "无消费者的历史会话治理快照",
    "specs/gates/metadata_client_codegen_pr_workflow.md": "无消费者的历史 PR 工作流说明",
    "specs/gates/alpha_beta_contract_seed_sessions.md": "仅与两份旧 Alpha/Beta 会话说明互引的退役执行记录",
    "specs/gates/assistant_alpha_beta_real_chain_spec.md": "已由四环境 seed manifest、正式 acceptance 与 runtime smoke 取代",
    "specs/gates/business_alpha_beta_db_seed_spec.md": "已由四环境 seed manifest、正式 acceptance 与三层测试策略取代",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_city_01.jpg": "与 archived 原始素材同哈希且无 source catalog 消费者",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_design_01.jpg": "与 archived 原始素材同哈希且无 source catalog 消费者",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_food_01.jpg": "与 archived 原始素材同哈希且无 source catalog 消费者",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_lifestyle_01.jpg": "与 archived 原始素材同哈希且无 source catalog 消费者",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_photography_01.jpg": "与 archived 原始素材同哈希且无 source catalog 消费者",
    "quwoquan_service/contracts/metadata/_shared/test_fixtures/original_media/portrait_legacy_travel_01.jpg": "与 archived 原始素材同哈希且无 source catalog 消费者",
    "quwoquan_service/runtime/agentpack/types.go": "仅承载已废止 agent_task_pack 的死类型，无生产调用方",
}

REVIEW_REQUIRED_PATHS: dict[str, str] = {}

RETAINED_PATHS = {
    "quwoquan_service/services/rec-model-service/scripts/requirements.txt": "训练、评估与样本处理 lane 的独立依赖清单，活动 CI 和训练镜像均显式消费",
    "quwoquan_ops/backup/pg_backup.sh": "宿主机 PostgreSQL 备份运维入口，保留环境变量注入和保留期清理能力",
    "quwoquan_ops/backup/mongo_backup.sh": "宿主机 MongoDB 备份运维入口，保留环境变量注入和保留期清理能力",
    "specs/gates/v6_git_branch_cleanup_decisions.md": "CR-20260531-028 直接引用的远程分支删除与可恢复 SHA 历史证据",
    "quwoquan_service/scripts/search/search_load_benchmark.py": "搜索容量验收仍在 feature-tree spec/acceptance 中声明的人工压测入口",
    "quwoquan_service/scripts/search/search_rollback_rehearsal.py": "搜索故障注入与恢复的已登记运维演练入口",
    "quwoquan_service/scripts/search/verify_search_local_gamma_capacity.py": "R-S06-S-1 已登记的 gamma-local 容量与可重复性验证入口",
}

CACHE_SEGMENTS = {
    ".dart_tool",
    ".gradle",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

PROTECTED_LOCAL_CONFIG_NAMES = {
    "credentials.json",
    "google-services.json",
    "GoogleService-Info.plist",
}
PROTECTED_LOCAL_CONFIG_SUFFIXES = {
    ".jks",
    ".keystore",
    ".p12",
    ".pem",
}

GENERATED_MARKERS = {
    "generated",
    "generated_manifest.json",
    "contract_graph.json",
}
REFERENCE_EXCLUDED_PATHS = {"quwoquan_ops/cli/repo_hygiene_audit.py"}


def _run_git(args: list[str]) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def _split_z(data: bytes) -> list[str]:
    return [item.decode("utf-8", errors="surrogateescape") for item in data.split(b"\0") if item]


def _tracked_paths() -> set[str]:
    return set(_split_z(_run_git(["ls-files", "-z"])))


def _status_paths() -> dict[str, str]:
    """返回 path -> porcelain XY，包含 ignored 与所有 untracked 文件。"""
    records = _split_z(
        _run_git(
            [
                "status",
                "--porcelain=v1",
                "--ignored",
                "--untracked-files=all",
                "-z",
            ]
        )
    )
    statuses: dict[str, str] = {}
    for record in records:
        # `git status --porcelain -z` 会为 rename/copy 将旧路径作为第二个、
        # 不带状态的 NUL 记录输出；不能把它解析成 `"qu"` 加截断路径。
        if len(record) < 4 or record[2] != " ":
            continue
        status = record[:2]
        path = record[3:]
        statuses[path] = status
    return statuses


def _disk_file_paths() -> set[str]:
    paths: set[str] = set()
    for current, directories, files in os.walk(ROOT, topdown=True):
        current_path = Path(current)
        directories[:] = [name for name in directories if name != ".git"]
        for name in directories:
            path = current_path / name
            if path.is_symlink():
                paths.add(path.relative_to(ROOT).as_posix())
        for name in files:
            paths.add((current_path / name).relative_to(ROOT).as_posix())
    return paths


def _ignored_paths(paths: set[str]) -> set[str]:
    if not paths:
        return set()
    payload = b"\0".join(
        path.encode("utf-8", errors="surrogateescape") for path in sorted(paths)
    ) + b"\0"
    result = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=ROOT,
        check=False,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(
            result.stderr.decode("utf-8", errors="replace").strip()
            or "git check-ignore failed"
        )
    return set(_split_z(result.stdout))


def _hash_file(path: Path, max_bytes: int | None) -> str | None:
    try:
        if max_bytes == 0:
            return None
        if not path.is_file() or path.is_symlink():
            return None
        size = path.stat().st_size
        if max_bytes is not None and size > max_bytes:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, ValueError):
        return None


def _empty_directories() -> list[str]:
    empty: list[str] = []
    for current, directories, files in os.walk(ROOT, topdown=True):
        current_path = Path(current)
        directories[:] = [name for name in directories if name != ".git"]
        if current_path != ROOT and not directories and not files:
            empty.append(current_path.relative_to(ROOT).as_posix())
    return sorted(empty)


def _reference_matches(path: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "grep",
            "-l",
            "--fixed-strings",
            "--",
            path,
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return [
        item
        for item in result.stdout.splitlines()
        if item and item != path and item not in REFERENCE_EXCLUDED_PATHS
    ][:20]


def _category(path: str, status: str, tracked: bool) -> tuple[str, str]:
    if status == "!!":
        name = Path(path).name
        if (
            name == ".env"
            or name.startswith(".env.")
            or name in PROTECTED_LOCAL_CONFIG_NAMES
            or Path(name).suffix.lower() in PROTECTED_LOCAL_CONFIG_SUFFIXES
        ):
            return (
                "protected_local_configuration",
                "被 Git 忽略的本机环境或凭据配置，不得按可再生产缓存自动清理",
            )
        return "reproducible_local_output", "被 Git 忽略或位于可再生产缓存/构建目录"
    if status.strip():
        return "protected_wip", f"当前 Git 状态为 {status!r}，清理批次硬排除"

    parts = Path(path).parts
    if any(part in CACHE_SEGMENTS for part in parts):
        return "reproducible_local_output", "被 Git 忽略或位于可再生产缓存/构建目录"

    if path.startswith("quwoquan_app/vendor/"):
        return "vendored_dependency", "App pubspec dependency_overrides 或平台构建引用的受控 vendor"

    if (
        "generated" in parts
        or Path(path).name in GENERATED_MARKERS
        or Path(path).name.endswith(".g.dart")
        or Path(path).name.endswith(".g.go")
    ):
        return "managed_generated", "位于生成目录或符合受保护生成产物命名，需由 generator/manifest 管理"

    if (
        path.startswith("quwoquan_service/contracts/")
        or path.startswith("quwoquan_data/control_plane/")
        or path.startswith("quwoquan_data/schema/")
        or path.startswith("quwoquan_data/reference/")
    ):
        return "runtime_or_fixture_asset", "契约、控制面、schema 或 reference 真相源"

    if tracked:
        return "reachable_source", "Git 跟踪源码/测试/配置，需以入口和引用证据继续判断"
    return "review_required_candidate", "未跟踪且不属于可自动判定的缓存或受保护资产"


def _iter_inventory(
    tracked: set[str],
    statuses: dict[str, str],
    hash_limit: int | None,
) -> Iterable[dict[str, object]]:
    paths = sorted(tracked | set(statuses))
    for path in paths:
        status = statuses.get(path, "  ")
        category, reason = _category(path, status, path in tracked)
        if path in HIGH_CONFIDENCE_PATHS and status in {"  ", "??", "!!"}:
            category = "high_confidence_retire"
            reason = HIGH_CONFIDENCE_PATHS[path]
        elif not status.strip() and path in REVIEW_REQUIRED_PATHS:
            category = "review_required_candidate"
            reason = REVIEW_REQUIRED_PATHS[path]
        elif not status.strip() and path in RETAINED_PATHS:
            category = "retained_operational_or_lane_dependency"
            reason = RETAINED_PATHS[path]

        disk_path = ROOT / path
        size = None
        is_file = False
        is_symlink = False
        try:
            is_symlink = disk_path.is_symlink()
            is_file = disk_path.is_file()
            if is_file:
                size = disk_path.stat().st_size
        except OSError:
            pass

        yield {
            "path": path,
            "git_status": status,
            "tracked": path in tracked,
            "ignored": status == "!!",
            "exists_on_disk": disk_path.exists() or disk_path.is_symlink(),
            "is_file": is_file,
            "is_symlink": is_symlink,
            "broken_symlink": is_symlink and not disk_path.exists(),
            "size_bytes": size,
            "sha256": _hash_file(disk_path, hash_limit),
            "category": category,
            "reason": reason,
        }


def _write_report(
    output_dir: Path,
    records: list[dict[str, object]],
    hash_limit: int | None,
    empty_directories: list[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = output_dir / "inventory.jsonl"
    with inventory_path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    by_category: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    bytes_by_category: Counter[str] = Counter()
    for record in records:
        category = str(record["category"])
        by_category[category] += 1
        by_status[str(record["git_status"])] += 1
        size = record["size_bytes"]
        if isinstance(size, int):
            bytes_by_category[category] += size

    candidates: list[dict[str, object]] = []
    for record in records:
        if record["category"] not in {
            "high_confidence_retire",
            "review_required_candidate",
        }:
            continue
        path = str(record["path"])
        candidates.append(
            {
                **record,
                "reference_matches": _reference_matches(path),
            }
        )

    largest_reproducible_outputs = sorted(
        (
            {
                "path": str(record["path"]),
                "size_bytes": int(record["size_bytes"]),
            }
            for record in records
            if record["category"] == "reproducible_local_output"
            and isinstance(record["size_bytes"], int)
        ),
        key=lambda item: item["size_bytes"],
        reverse=True,
    )[:25]
    zero_byte_tracked_files = sorted(
        str(record["path"])
        for record in records
        if record["tracked"]
        and record["is_file"]
        and record["size_bytes"] == 0
    )
    broken_symlinks = sorted(
        str(record["path"])
        for record in records
        if record["broken_symlink"]
    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(ROOT),
        "command": "python3 quwoquan_ops/cli/repo_hygiene_audit.py",
        "hash_policy": {
            "sha256_generated_for_files_up_to_bytes": hash_limit,
            "large_or_unreadable_files_have_null_sha256": True,
        },
        "record_count": len(records),
        "category_counts": dict(sorted(by_category.items())),
        "category_bytes": dict(sorted(bytes_by_category.items())),
        "git_status_counts": dict(sorted(by_status.items())),
        "high_confidence_candidates": [
            item for item in candidates if item["category"] == "high_confidence_retire"
        ],
        "review_required_candidates": [
            item for item in candidates if item["category"] == "review_required_candidate"
        ],
        "largest_reproducible_local_outputs": largest_reproducible_outputs,
        "zero_byte_tracked_files": zero_byte_tracked_files,
        "broken_symlinks": broken_symlinks,
        "empty_directories": empty_directories,
        "wip_paths": [
            str(record["path"])
            for record in records
            if record["category"] == "protected_wip"
        ],
        "inventory_file": inventory_path.name,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读生成全仓目录整洁审计 inventory 与 summary"
    )
    parser.add_argument(
        "--output-dir",
        help="报告目录；默认写入 .qwq_output/env/repo/runs/<timestamp>-repo-hygiene-audit-repo",
    )
    parser.add_argument(
        "--hash-mode",
        choices=("none", "small", "all"),
        default="small",
        help="哈希范围：none、small（默认 1MiB 内）或 all",
    )
    parser.add_argument(
        "--max-hash-bytes",
        type=int,
        default=1024 * 1024,
        help="hash-mode=small 时允许计算 SHA-256 的最大文件大小",
    )
    args = parser.parse_args()

    tracked = _tracked_paths()
    disk_paths = _disk_file_paths()
    statuses = _status_paths()
    for path in _ignored_paths(disk_paths - tracked):
        statuses[path] = "!!"
    for path in disk_paths - tracked - set(statuses):
        statuses[path] = "??"
    if args.hash_mode == "none":
        hash_limit = 0
    elif args.hash_mode == "all":
        hash_limit = None
    else:
        hash_limit = max(0, args.max_hash_bytes)

    records = list(_iter_inventory(tracked, statuses, hash_limit))
    empty_directories = _empty_directories()
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else repo_run_dir("repo-hygiene-audit", target="repo")
    )
    _write_report(output_dir, records, hash_limit, empty_directories)

    print(
        json.dumps(
            {
                "reportDir": str(output_dir.relative_to(ROOT))
                if output_dir.is_relative_to(ROOT)
                else str(output_dir),
                "recordCount": len(records),
                "highConfidenceCount": sum(
                    record["category"] == "high_confidence_retire"
                    for record in records
                ),
                "wipCount": sum(
                    record["category"] == "protected_wip" for record in records
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
