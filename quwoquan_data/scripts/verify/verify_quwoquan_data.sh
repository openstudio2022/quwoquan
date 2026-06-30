#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
PYTEST_RUNNER="${PYTEST_RUNNER:-$ROOT/quwoquan_data/.venv/bin/python}"
if [ ! -x "$PYTEST_RUNNER" ]; then
  PYTEST_RUNNER="${PYTHON:-python3}"
fi

# CLI-first ratchet：拦截新增直跑业务入口脚本（必须经 qwq-data 暴露给 skill）
python3 quwoquan_data/scripts/verify/verify_cli_first.py
python3 quwoquan_data/scripts/verify/verify_creator_pool_contract.py
python3 quwoquan_data/scripts/verify/verify_creator_pool_seed_consistency.py
python3 quwoquan_data/scripts/verify/verify_prefab_user_provenance.py
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/local_contract/creator_pool/
python3 quwoquan_data/scripts/cli.py verify data-role-gate
python3 quwoquan_data/scripts/verify/verify_no_flat_roots.py
# 单一门库 quality_gates：writingIntent 契约 + 图文闭环 + 写作主线一致性 + 模板骨架相似度 + 语域 + source reject 阻断
python3 quwoquan_data/tests/common/test_quality_gates.py
# 简体中文发布门：发布标题/正文/caption 必须简体中文(非中文先译中、繁体折叠简体)；
#                繁简折叠表与拉丁主导阈值单一真相源(_common.localization)，caption 门与主页门共用
python3 quwoquan_data/tests/common/test_localization_simplified_chinese.py
# 扫描门：禁止 scripts/tasks/runtime 复用测试专用正文骨架 agent_draft_kit（脚本拼文章正文反模式），
#         并禁止重新引入「脚本拼实体主页正文」机械骨架函数（主页 page.md 须 Agent 创作）。
python3 quwoquan_data/scripts/verify/verify_no_runtime_draft_kit.py
python3 quwoquan_data/tests/verify/test_no_runtime_draft_kit.py
# object-stage job 队列：幂等/lease/崩溃恢复/同源互斥/失败升级
python3 quwoquan_data/tests/task/test_object_queue.py
# 生产级内容供给闭环：current 契约 / reliabletask 后端 / AgentResultEnvelope / token ledger
python3 quwoquan_data/scripts/cli.py verify single-contract-source
python3 quwoquan_data/scripts/cli.py verify content-supply-production
# 作品 vs 随记判定契约：works_classification schema/config/registry 一致性 + 判定 smoke
python3 quwoquan_data/scripts/cli.py verify works-classification
python3 quwoquan_data/tests/verify/test_scale_readiness.py
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/site_supply/test_cli_works_classifier__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_content_plan_bridge__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_crawler_search__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_downstream_evidence__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_fetch_evidence__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_frontier_rollup__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_target_resolution__local_contract_test.py
python3 quwoquan_data/tests/verify/test_site_scale_readiness.py
# Subagent handoff packet 与出口门（single ref gate + batch reducer gate + 执行合约 5 要素）
python3 quwoquan_data/tests/common/test_handoff.py
# LLM-as-judge 严格性门：判官元数据 pin / 族分离 / 二元+理由 / 偏差缓解 / jury 多数表决 / kappa
python3 quwoquan_data/tests/common/test_rubric_judge.py
# 内容漂移检测 + golden 闭环自增长（sample-drift / promote-golden 幂等）
python3 quwoquan_data/tests/common/test_content_drift.py
# Harness sensor 钩子：subagentStart / beforeShellExecution / afterFileEdit（observe-only 始终 allow）
python3 quwoquan_data/tests/task/test_harness_hooks.py
# 证据准入门：source_screen=reject 来源不得进入 content_plan
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/common/test_base_draft_fidelity__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_content_plan_distribution__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_content_plan_source_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_prompt_render__local_contract_test.py
# golden set 标定：好稿/坏稿语义门拦截率/误杀率达标
python3 quwoquan_data/scripts/verify/measure_gate_goldenset.py
# 契约门：会话 agent = 唯一模型执行者（禁外部 LLM SDK/端点 + 交付正文 agent-only 防线）
python3 quwoquan_data/tests/common/test_agent_executor_contract.py
python3 quwoquan_data/scripts/cli.py template lint
# P1 提示词模板 lint：占位符闭合 / vars 必填 / 行数预算 / scripts 不得硬编码 prompt 正文（含 会话模型 措辞 ratchet）
python3 quwoquan_data/scripts/verify/verify_prompt_templates.py
python3 quwoquan_data/scripts/cli.py template creator-lint
python3 quwoquan_data/scripts/cli.py template rec-contract
python3 quwoquan_data/scripts/cli.py template audience-lint
# 虚拟作者内容感知匹配：底稿信号(范围/载体/题材)择优 + 区域>全国 + 载体偏向 + 单候选稳定 + 确定性
python3 quwoquan_data/tests/template/test_creator_match.py
# 收紧扫描范围：只校验发布面 posts 根
python3 quwoquan_data/scripts/cli.py verify --scope current
# 任务工程：committed 任务规格校验（路径↔id、archetype scope、实体类型真相源、重复）
python3 quwoquan_data/scripts/cli.py task lint
# 垂类规模化治理：coverage registry / 脚本目录 / golden samples / 摄影版权策略
python3 quwoquan_data/scripts/cli.py vertical governance
python3 quwoquan_data/scripts/cli.py vertical source-registry
python3 quwoquan_data/scripts/cli.py vertical quality
# 任务工程 + 采样回填契约测试
python3 quwoquan_data/tests/task/test_task_cli.py
python3 quwoquan_data/tests/ship/test_ship_sampling.py
# 环境数据发布契约：release artifact + 引用闭包 + 生产硬删除审批门
python3 quwoquan_data/tests/ship/test_data_release_consistency.py
# 垂类规模化成熟度：coverage registry / 版权门 / queue / post-activation / benchmark
python3 quwoquan_data/tests/vertical/test_vertical_maturity.py
# Phase 0：download 预置 source_plan 可消费（默认零源 bug 回归）
python3 quwoquan_data/tests/bootstrap/test_phase0_reverify.py
python3 quwoquan_data/tests/download/test_download_source_plan.py
# Phase 1：download 真实下图（sniff/curated/fetch_image/handler 接线）
python3 quwoquan_data/tests/download/test_download_images.py
# Phase 1：build 实体主页真实链路（prepare 下发契约 + validate 采纳门）
python3 quwoquan_data/tests/build/test_build_homepage.py
# 实体主页=百科择优单源（维基>百度>搜狗）+ 三件套同源 + 禁游记 + 发布完整性门
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/verify/test_release_integrity_gate.py
# Phase 1：实体主页图片闭环全量扫描/修复（page.md ↔ manifest.assets ↔ assets/）
python3 quwoquan_data/tests/homepage_assets/test_homepage_assets.py
python3 quwoquan_data/scripts/cli.py homepage-assets --dirty-only --fail-on-issues --include-runtime --include-publish
# 实体主页结构(原文关键章节覆盖) + 配图 caption 语义门（新批次 opt-in：batch_manifest.homepageStructureGate=true）
python3 quwoquan_data/scripts/verify/verify_homepage_structure_and_assets.py --all-runtime-opt-in
# 历史脏数据：工程污染主页 / 伪图片 / 悬空 asset 必须清零
python3 quwoquan_data/tests/quality/test_dirty_data_cleanup.py
python3 quwoquan_data/scripts/cli.py quality dirty-scan --fail-on-issues
# Phase 1：无人值守 workflow 编排 DAG（三层测试：local_contract/api_integration/user_acceptance）
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/cli/test_cli_environment__local_contract_test.py \
  quwoquan_data/tests/local_contract/cli/test_cli_finalize_author__local_contract_test.py \
  quwoquan_data/tests/local_contract/cli/test_cli_verify_audit__local_contract_test.py \
  quwoquan_data/tests/local_contract/cli/test_cli_workflow_commands__local_contract_test.py
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/build/test_homepage_prepare__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_auto_content_plan__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_content_plan_source_contract__local_contract_test.py \
  quwoquan_data/tests/local_contract/produce/test_task_author_review__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_download_auto_research__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_download_checkpoint_repair__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_download_fast_fail_policy__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_download_repair_prompt__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_managed_local_runtime__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_managed_preflight_workspace__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_replacement_screening__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_workflow_state_machine__local_contract_test.py \
  quwoquan_data/tests/api_integration/ship/test_task_publish_release__api_integration_test.py \
  quwoquan_data/tests/user_acceptance/workflow/test_task_run_operator_journey__user_acceptance_test.py
# Phase 1：HITL 最小化（明确违规自动丢弃/明确合格自动采纳/仅模糊项转人工）
python3 quwoquan_data/tests/integration/test_hitl_autopass.py
# Phase 1：实体 composer 红绿契约 + entityRef 全路径回归（发布门主实体不被误过滤）
python3 quwoquan_data/tests/produce/test_entity_composer.py
# 线路 brief + 证据 + route 单一多目的地底稿模型（每目的地节点各自单一底稿、节点内不跨源）
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/produce/test_route_brief_and_evidence.py
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
# 创作自治：creativeBrief 下发 + creativePlan/selfCritique 回写 + persona 边界门
python3 quwoquan_data/tests/produce/test_creative_autonomy_gate.py
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
# RC3 图文混排：HTML 内联<img>就地同源捕获(抽取器分发/相对解析/data:跳过/payload清单)
# + 内联候选构建与五道硬门后回连段落占位(同源不绕许可)
python3 quwoquan_data/tests/download/test_fetch_registry_dispatch.py
python3 quwoquan_data/tests/local_contract/download/test_inline_source_images__local_contract_test.py
# P2 连续图组（figuregroup）回填契约：expand 回填/带回完整性/绑定后清理/计数/净化保结构
python3 quwoquan_data/tests/local_contract/common/test_figure_group_backfill__local_contract_test.py
# 标签可点击态：tag 本体保持语义定义，link target 由 publish index 派生
python3 quwoquan_data/tests/publish/test_tag_link_targets.py
# 行政区标签层级：V1 中国两级选择依赖 34 省级、广东完整地级市、北京区县 direct children
python3 quwoquan_data/tests/local_contract/publish/test_admin_region_tags__local_contract_test.py
# 结构化出处：5.review/provenance.json 统一回查入口（agent 输入/最终结果/原始源/证据源/门结果）+ 强制完整性/一致性门
python3 quwoquan_data/tests/common/test_provenance.py
# 实体标注：词典 grounding + inline 机械标注（首次出现/frontmatter 安全）+ ref 闭环强校验 + 发布强制覆盖门
python3 quwoquan_data/tests/common/test_entity_annotation.py
# 「明」交集信号：intersectionHints 对齐 IntersectionReason 闭集/字段 + 维度完备性 + 锚点闭环门
python3 quwoquan_data/tests/common/test_intersection_signal.py
# 单会话多实体批处理：批 prompt 打包 N 实体（聚合 writing_pack + 跨篇多样性约束）+ 完整性/完成度
python3 quwoquan_data/tests/common/test_batch_orchestration.py
# Fan-out 编排脚手架：计划构建/去重/互斥/覆盖/冻结门
python3 quwoquan_data/tests/orchestrate/test_fanout_plan.py
# Fan-out 四策略展开（by-partition / flat-pool / by-leaf / by-batch）确定性 + 不变量
python3 quwoquan_data/tests/orchestrate/test_fanout_strategies.py
# Fan-out 调度：冻结门 + 建 task/batch + 入队叶子 + 幂等可重放 + rollup 聚合
python3 quwoquan_data/tests/orchestrate/test_fanout_dispatch.py
# Fan-out 退化等价：--mode fanout --concurrency 1 --strategy flat-pool 与 single 同终态
python3 quwoquan_data/tests/orchestrate/test_mode_single_fanout_equivalence.py
# Fan-out 外部 runner（mock SDK）：lease→complete 回写、startup vs run 失败分流、用量/预算门
python3 quwoquan_data/tests/orchestrate/test_fanout_runner.py
# 百科多层目录 + 章节配图 + 对象阶段树 + wikitext 锚点（新批次验收）
python3 quwoquan_data/tests/local_contract/common/test_section_outline_and_placement__local_contract_test.py
python3 quwoquan_data/tests/local_contract/common/test_object_stages_and_wikitext__local_contract_test.py
# 底稿忠实重构 + 无人托管可靠性（P0 探针分类、key 单一真相源、scaled-e2e 续跑、
# RC2/RC4/RC6 同源硬门、形态自适应字数门、实体聚焦、多地点 route 死代码收口）
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/env/test_cursor_probe__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_cursor_credentials__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_scaled_e2e_run__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_sandbox_root_isolation__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_adaptive_word_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_entity_focus__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_source_quality_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_image_collection_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_source_plan_registry_guidance__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_auto_research_article_homepage__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_auto_research_image_lane__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_auto_research_transport__local_contract_test.py \
  quwoquan_data/tests/local_contract/produce/test_route_assets_layout__local_contract_test.py

echo "[verify-quwoquan-data] PASSED"
