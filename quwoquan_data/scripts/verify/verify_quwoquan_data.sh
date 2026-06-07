#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

# CLI-first ratchet：拦截新增直跑业务入口脚本（必须经 qwq-data 暴露给 skill）
python3 quwoquan_data/scripts/verify/verify_cli_first.py
python3 quwoquan_data/scripts/verify/verify_no_flat_roots.py
# 契约门：会话 agent = 唯一模型执行者（禁外部 LLM SDK/端点 + 交付正文 agent-only 防线）
python3 quwoquan_data/tests/common/test_agent_executor_contract.py
python3 quwoquan_data/scripts/cli.py template lint
python3 quwoquan_data/scripts/cli.py template creator-lint
python3 quwoquan_data/scripts/cli.py template rec-contract
python3 quwoquan_data/scripts/cli.py template region-season-lint
# 收紧扫描范围：只校验发布面 posts 根
python3 quwoquan_data/scripts/cli.py verify --scope current
# 任务工程：committed 任务规格校验（路径↔id、archetype scope、实体类型真相源、重复）
python3 quwoquan_data/scripts/cli.py task lint
# 垂类规模化治理：coverage registry / 脚本目录 / golden samples / 摄影版权策略
python3 quwoquan_data/scripts/cli.py vertical governance
python3 quwoquan_data/scripts/cli.py vertical quality
# 任务工程 + 采样回填契约测试
python3 quwoquan_data/tests/task/test_task_cli.py
python3 quwoquan_data/tests/ship/test_ship_sampling.py
# 环境数据发布契约：release artifact + 引用闭包 + 生产硬删除审批门
python3 quwoquan_data/tests/ship/test_data_release_consistency.py
# 垂类规模化成熟度：coverage registry / 版权门 / queue / post-activation / benchmark
python3 quwoquan_data/tests/vertical/test_vertical_maturity.py
# Phase 0：sop few-shot 注入 + download 预置 source_plan 可消费（默认零源 bug 回归）
python3 quwoquan_data/tests/bootstrap/test_phase0_reverify.py
python3 quwoquan_data/tests/bootstrap/test_sop_injection.py
python3 quwoquan_data/tests/download/test_download_source_plan.py
# Phase 1：download 真实下图（sniff/curated/fetch_image/handler 接线）
python3 quwoquan_data/tests/download/test_download_images.py
# Phase 1：build 实体主页真实链路（prepare 下发契约 + validate 采纳门）
python3 quwoquan_data/tests/build/test_build_homepage.py
# Phase 1：实体主页图片闭环全量扫描/修复（page.md ↔ manifest.assets ↔ assets/）
python3 quwoquan_data/tests/homepage_assets/test_homepage_assets.py
python3 quwoquan_data/scripts/cli.py homepage-assets --dirty-only --fail-on-issues --include-runtime --include-publish
# 历史脏数据：工程污染主页 / 伪图片 / 悬空 asset 必须清零
python3 quwoquan_data/tests/quality/test_dirty_data_cleanup.py
python3 quwoquan_data/scripts/cli.py quality dirty-scan --fail-on-issues
# Phase 1：无人值守 workflow 编排 DAG（checkpoint 暂停/resume 推进/--until 早停/task_workflow_state 幂等）
python3 quwoquan_data/tests/cli/test_data_cli.py
python3 quwoquan_data/tests/workflow/test_task_run_pipeline.py
# Phase 1：HITL 最小化（明确违规自动丢弃/明确合格自动采纳/仅模糊项转人工）
python3 quwoquan_data/tests/integration/test_hitl_autopass.py
# Phase 1：实体 composer 红绿契约 + entityRef 全路径回归（发布门主实体不被误过滤）
python3 quwoquan_data/tests/produce/test_entity_composer.py
# 内容质量：asset:// 引用闭环（引用↔manifest↔fileName↔物理文件↔sha256）+ assetId 可读化 + gallery caption 语义化
python3 quwoquan_data/tests/common/test_asset_refs.py
# 资产 ID 真相源：新命名格式、右锚定解析、跨批次变换
python3 quwoquan_data/tests/common/test_asset_id_stability.py
# 媒体发布：asset://→manifest→objectKey→cdnUrl + collision ledger 防覆盖
python3 quwoquan_data/tests/media/test_media_asset_url.py
python3 quwoquan_data/scripts/verify/verify_media_release_contract.py
# 源覆盖：旅游/校园源类别注册表归类 + 源类别覆盖门（「全」）+ catalog 结构 lint
python3 quwoquan_data/tests/template/test_source_catalog.py
# 文风开篇：styleFamily 多开篇策略自选 + 按所选族语义化检测 + 开篇引导下发 + catalog 结构 lint
python3 quwoquan_data/tests/template/test_style_catalog.py
# 文风门：开篇钩子语义化（按所选 styleFamily/openingStrategy）+ 跨篇相似度门（破量产千篇一律）
python3 quwoquan_data/tests/produce/test_style_gates.py
# 文章目录：posts/<type>/<发布标题>/<seq>/（标题在 article 之下、序号默认 1、标题重复递增、与 promote 对齐）
python3 quwoquan_data/tests/produce/test_post_dir_layout.py
# 对象同构目录：entities/posts 与 publish 同构 + 过程阶段编号 + 来源单元 + 相对路径 helper
python3 quwoquan_data/tests/common/test_batch_object_paths.py
# M2 对象优先：source_plan 落实体对象 1.download + 批次级公共信息上提（batch_manifest + _shared/source_catalog）
python3 quwoquan_data/tests/common/test_batch_shared_artifacts.py
# 全局批次号 / 批内 registry / 双批稳定性
python3 quwoquan_data/tests/common/test_global_batch_seq.py
python3 quwoquan_data/tests/common/test_batch_asset_registry.py
python3 quwoquan_data/tests/common/test_batch_asset_stability.py
# M3 对象优先：内容对象路由 ref → posts/{type}/{angle}/{title}/{seq} + _shared 路由索引
python3 quwoquan_data/tests/common/test_content_object_router.py
# 资产证据链：来源单元 → 文章 asset:// → 成品 assets（assetId 文件名）→ 相对 sourceAssetRef 可回查
python3 quwoquan_data/tests/common/test_source_unit_evidence_chain.py
# 目录与资产静态门 + 文风门：散落 images/、绝对路径、机械收尾标题、无类别 weather 来源全阻断
python3 quwoquan_data/tests/verify/test_directory_evidence_gate.py
# 图片下载 6 门：相关性必填非模板、每实体≥2、最小像素、contentType+版权持久化、多变体(webp)、感知去重
python3 quwoquan_data/tests/download/test_image_download_gates.py
# 标签可点击态：tag 本体保持语义定义，link target 由 publish index 派生
python3 quwoquan_data/tests/publish/test_tag_link_targets.py
# 结构化出处：5.review/provenance.json 统一回查入口（agent 输入/最终结果/原始源/证据源/门结果）+ 强制完整性/一致性门
python3 quwoquan_data/tests/common/test_provenance.py
# 实体标注：词典 grounding + inline 机械标注（首次出现/frontmatter 安全）+ ref 闭环强校验 + 发布强制覆盖门
python3 quwoquan_data/tests/common/test_entity_annotation.py
# 「明」交集信号：intersectionHints 对齐 IntersectionReason 闭集/字段 + 维度完备性 + 锚点闭环门
python3 quwoquan_data/tests/common/test_intersection_signal.py
# 单会话多实体批处理：批 prompt 打包 N 实体（聚合 writing_pack + 跨篇多样性约束）+ 完整性/完成度
python3 quwoquan_data/tests/common/test_batch_orchestration.py

echo "[verify-quwoquan-data] PASSED"
