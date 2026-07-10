#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"
PYTEST_RUNNER="${PYTEST_RUNNER:-$ROOT/quwoquan_data/.venv/bin/python}"
if [ ! -x "$PYTEST_RUNNER" ]; then
  PYTEST_RUNNER="${PYTHON:-python3}"
fi
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
DATA_VERIFY_OUTPUT_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/qwq_data_verify_output.XXXXXX")"
trap 'rm -rf "$DATA_VERIFY_OUTPUT_ROOT"' EXIT
# 整个 data gate 的运行期输出都进临时根，避免直跑 Python/CLI 段污染真实
# .qwq_output/data/**；pytest 进程内会由 tests/conftest.py 进一步隔离。
export QWQ_OUTPUT_ROOT="$DATA_VERIFY_OUTPUT_ROOT"

# 全量 data gate 必须在安静工作区运行：活跃 run-recipe/scaled-e2e/workflow
# 会合法写 runtime/publish 证据，导致 pytest 隔离门把外部写入误判为测试泄漏。
python3 quwoquan_data/scripts/verify/verify_no_active_data_runtime.py

# CLI-first ratchet：拦截新增直跑业务入口脚本（必须经 qwq-data 暴露给 skill）
python3 quwoquan_data/scripts/cli.py verify data-layout
python3 quwoquan_data/scripts/verify/verify_cli_first.py
python3 quwoquan_data/scripts/verify/verify_creator_pool_contract.py
python3 quwoquan_data/scripts/verify/verify_creator_pool_seed_consistency.py
python3 quwoquan_data/scripts/verify/verify_prefab_user_provenance.py
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/local_contract/creator_pool/
python3 quwoquan_data/scripts/cli.py verify data-role-gate
python3 quwoquan_data/scripts/verify/verify_no_flat_roots.py
# 仓外输出根隔离门：repo 仅 publish 可入库生成输出 + canonical 批次轴/committed 回指 + artifacts index-first
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
# 单一门库 quality_gates：writingIntent 契约 + 图文闭环 + 写作主线一致性 + 模板骨架相似度 + 语域 + source reject 阻断
python3 quwoquan_data/tests/local_contract/common/test_quality_gates__local_contract_test.py
# 简体中文发布门：发布标题/正文/caption 必须简体中文(非中文先译中、繁体折叠简体)；
#                繁简折叠表与拉丁主导阈值单一真相源(_common.localization)，caption 门与主页门共用
python3 quwoquan_data/tests/local_contract/common/test_localization_simplified_chinese__local_contract_test.py
# 扫描门：禁止 scripts/tasks/runtime 复用测试专用正文骨架 agent_draft_kit（脚本拼文章正文反模式），
#         并禁止重新引入「脚本拼实体主页正文」机械骨架函数（主页 page.md 须 Agent 创作）。
python3 quwoquan_data/scripts/verify/verify_no_runtime_draft_kit.py
python3 quwoquan_data/tests/local_contract/verify/test_no_runtime_draft_kit__local_contract_test.py
# object-stage job 队列：幂等/lease/崩溃恢复/同源互斥/失败升级
python3 quwoquan_data/tests/local_contract/task/test_object_queue__local_contract_test.py
# 生产级内容供给闭环：current 契约 / reliabletask 后端 / AgentResultEnvelope / token ledger
python3 quwoquan_data/scripts/cli.py verify single-contract-source
python3 quwoquan_data/scripts/cli.py verify content-supply-production
# 作品 vs 随记判定契约：works_classification schema/config/registry 一致性 + 判定 smoke
python3 quwoquan_data/scripts/cli.py verify works-classification
python3 quwoquan_data/tests/local_contract/verify/test_scale_readiness__local_contract_test.py
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/site_supply/test_cli_works_classifier__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_content_plan_bridge__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_crawler_search__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_downstream_evidence__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_fetch_evidence__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_frontier_rollup__local_contract_test.py \
  quwoquan_data/tests/local_contract/site_supply/test_target_resolution__local_contract_test.py
python3 quwoquan_data/tests/local_contract/verify/test_site_scale_readiness__local_contract_test.py
# Subagent handoff packet 与出口门（single ref gate + batch reducer gate + 执行合约 5 要素）
python3 quwoquan_data/tests/local_contract/common/test_handoff__local_contract_test.py
# LLM-as-judge 严格性门：判官元数据 pin / 族分离 / 二元+理由 / 偏差缓解 / jury 多数表决 / kappa
python3 quwoquan_data/tests/local_contract/common/test_rubric_judge__local_contract_test.py
# 内容漂移检测 + golden 闭环自增长（sample-drift / promote-golden 幂等）
python3 quwoquan_data/tests/local_contract/common/test_content_drift__local_contract_test.py
# Harness sensor 钩子：subagentStart / beforeShellExecution / afterFileEdit（observe-only 始终 allow）
python3 quwoquan_data/tests/local_contract/task/test_harness_hooks__local_contract_test.py
# 证据准入门：source_screen=reject 来源不得进入 content_plan
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/common/test_base_draft_fidelity__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_content_plan_distribution__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_content_plan_source_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_prompt_render__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_source_structure_fidelity__local_contract_test.py
# golden set 标定：好稿/坏稿语义门拦截率/误杀率达标
python3 quwoquan_data/scripts/verify/measure_gate_goldenset.py
# 契约门：会话 agent = 唯一模型执行者（禁外部 LLM SDK/端点 + 交付正文 agent-only 防线）
python3 quwoquan_data/tests/local_contract/common/test_agent_executor_contract__local_contract_test.py
python3 quwoquan_data/scripts/cli.py template lint
# P1 提示词模板 lint：占位符闭合 / vars 必填 / 行数预算 / scripts 不得硬编码 prompt 正文（含 会话模型 措辞 ratchet）
python3 quwoquan_data/scripts/verify/verify_prompt_templates.py
python3 quwoquan_data/scripts/cli.py template creator-lint
python3 quwoquan_data/scripts/cli.py template rec-contract
python3 quwoquan_data/scripts/cli.py template audience-lint
# 虚拟作者内容感知匹配：底稿信号(范围/载体/题材)择优 + 区域>全国 + 载体偏向 + 单候选稳定 + 确定性
python3 quwoquan_data/tests/local_contract/template/test_creator_match__local_contract_test.py
# 收紧扫描范围：只校验发布面 posts 根
python3 quwoquan_data/scripts/cli.py verify --scope current
# 任务工程：committed 任务规格校验（路径↔id、archetype scope、实体类型真相源、重复）
python3 quwoquan_data/scripts/cli.py task lint
# 全国地点主清单门禁（discovery_seed/2）：目录归属/schema 同口径/类型 scope/行政区叶子/canonicalName 全局唯一
python3 quwoquan_data/scripts/cli.py verify coverage-master-list
# WP1 契约测试：主清单 schema/C1-C9 反例门 + 类型唯一真相源（裁决 6 优先级表 + 收债 9 口径归一 + _entity.json 必填集不漂移）
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/verify/test_coverage_master_list__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_entity_type_taxonomy__local_contract_test.py
# 垂类规模化治理：coverage registry / 脚本目录 / golden samples / 摄影版权策略
python3 quwoquan_data/scripts/cli.py vertical governance
python3 quwoquan_data/scripts/cli.py vertical source-registry
python3 quwoquan_data/scripts/cli.py vertical quality
# 任务工程 + 采样回填契约测试
python3 quwoquan_data/tests/local_contract/task/test_task_cli__local_contract_test.py
# 任务控制面：preset/recipe 契约（lint 全量家族包 + presetRef 合并 + run-recipe 四段主干 + 契约门阻断）
python3 quwoquan_data/tests/local_contract/task/test_task_recipe__local_contract_test.py
python3 quwoquan_data/tests/api_integration/ship/test_ship_sampling__api_integration_test.py
# 环境数据发布契约：release artifact + 引用闭包 + 生产硬删除审批门
python3 quwoquan_data/tests/api_integration/ship/test_data_release_consistency__api_integration_test.py
# 垂类规模化成熟度：coverage registry / 版权门 / queue / post-activation / benchmark
python3 quwoquan_data/tests/local_contract/vertical/test_vertical_maturity__local_contract_test.py
# Phase 0：download 预置 source_plan 可消费（默认零源 bug 回归）
python3 quwoquan_data/tests/local_contract/bootstrap/test_phase0_reverify__local_contract_test.py
python3 quwoquan_data/tests/local_contract/download/test_download_source_plan__local_contract_test.py
# Phase 1：download 真实下图（sniff/curated/fetch_image/handler 接线）
python3 quwoquan_data/tests/local_contract/download/test_download_images__local_contract_test.py
# Phase 1：build 实体主页真实链路（prepare 下发契约 + validate 采纳门）
python3 quwoquan_data/tests/local_contract/build/test_build_homepage__local_contract_test.py
# 实体主页=主权威百科单源择优（维基百科/维基导游/百度/搜狗）+ 三件套同源 + 禁游记 + 发布完整性门
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/user_acceptance/verify/test_release_integrity_gate__user_acceptance_test.py
# Phase 1：实体主页图片闭环全量扫描/修复（page.md ↔ manifest.assets ↔ assets/）
python3 quwoquan_data/tests/local_contract/homepage_assets/test_homepage_assets__local_contract_test.py
python3 quwoquan_data/scripts/cli.py homepage-assets --dirty-only --fail-on-issues --include-runtime --include-publish
# 实体主页结构(原文关键章节覆盖) + 配图 caption 语义门（新批次 opt-in：batch_manifest.homepageStructureGate=true）
python3 quwoquan_data/scripts/verify/verify_homepage_structure_and_assets.py --all-runtime-opt-in
# 历史脏数据：工程污染主页 / 伪图片 / 悬空 asset 必须清零
python3 quwoquan_data/tests/local_contract/quality/test_dirty_data_cleanup__local_contract_test.py
python3 quwoquan_data/scripts/cli.py quality dirty-scan --fail-on-issues
# Phase 1：无人值守 workflow 编排 DAG（三层测试：local_contract/api_integration/user_acceptance）
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/cli/test_cli_environment__local_contract_test.py \
  quwoquan_data/tests/local_contract/cli/test_cli_finalize_author__local_contract_test.py \
  quwoquan_data/tests/local_contract/cli/test_cli_verify_audit__local_contract_test.py \
  quwoquan_data/tests/local_contract/cli/test_cli_verify_sdk_monitoring__local_contract_test.py \
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
python3 quwoquan_data/tests/api_integration/integration/test_hitl_autopass__api_integration_test.py
# Phase 1：实体 composer 红绿契约 + entityRef 全路径回归（发布门主实体不被误过滤）
python3 quwoquan_data/tests/local_contract/produce/test_entity_composer__local_contract_test.py
# 线路 brief + 证据 + route 单一多目的地底稿模型（每目的地节点各自单一底稿、节点内不跨源）
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/local_contract/produce/test_route_brief_and_evidence__local_contract_test.py
# 内容质量：asset:// 引用闭环（引用↔manifest↔fileName↔物理文件↔sha256）+ assetId 可读化 + gallery caption 语义化
python3 quwoquan_data/tests/local_contract/common/test_asset_refs__local_contract_test.py
# 资产 ID 真相源：新命名格式、右锚定解析、跨批次变换
python3 quwoquan_data/tests/local_contract/common/test_asset_id_stability__local_contract_test.py
# 媒体发布：asset://→manifest→objectKey→cdnUrl + collision ledger 防覆盖
python3 quwoquan_data/tests/local_contract/media/test_media_asset_url__local_contract_test.py
python3 quwoquan_data/scripts/verify/verify_media_release_contract.py
# 源覆盖：旅游/校园源类别注册表归类 + 源类别覆盖门（「全」）+ catalog 结构 lint
python3 quwoquan_data/tests/local_contract/template/test_source_catalog__local_contract_test.py
# 文风开篇：styleFamily 多开篇策略自选 + 按所选族语义化检测 + 开篇引导下发 + catalog 结构 lint
python3 quwoquan_data/tests/local_contract/template/test_style_catalog__local_contract_test.py
# 文风门：开篇钩子语义化（按所选 styleFamily/openingStrategy）+ 跨篇相似度门（破量产千篇一律）
python3 quwoquan_data/tests/local_contract/produce/test_style_gates__local_contract_test.py
# 创作自治：creativeBrief 下发 + creativePlan/selfCritique 回写 + persona 边界门
python3 quwoquan_data/tests/local_contract/produce/test_creative_autonomy_gate__local_contract_test.py
# 文章目录：posts/<type>/<发布标题>/<seq>/（标题在 article 之下、序号默认 1、标题重复递增、与 promote 对齐）
python3 quwoquan_data/tests/local_contract/produce/test_post_dir_layout__local_contract_test.py
# 对象同构目录：entities/posts 与 publish 同构 + 过程阶段编号 + 来源单元 + 相对路径 helper
python3 quwoquan_data/tests/local_contract/common/test_batch_object_paths__local_contract_test.py
# M2 对象优先：source_plan 落实体对象 1.download + 批次级公共信息上提（batch_manifest + _shared/source_catalog）
python3 quwoquan_data/tests/local_contract/common/test_batch_shared_artifacts__local_contract_test.py
# 跨批去重账本：文件锁并发不丢更新 + 幂等 + 全国维度常量（多省并行前置）
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/local_contract/common/test_dedup_ledger__local_contract_test.py
# 全局批次号 / 批内 registry / 双批稳定性
python3 quwoquan_data/tests/local_contract/common/test_global_batch_seq__local_contract_test.py
python3 quwoquan_data/tests/local_contract/common/test_batch_asset_registry__local_contract_test.py
python3 quwoquan_data/tests/local_contract/common/test_batch_asset_stability__local_contract_test.py
# M3 对象优先：内容对象路由 ref → posts/{type}/{angle}/{title}/{seq} + _shared 路由索引
python3 quwoquan_data/tests/local_contract/common/test_content_object_router__local_contract_test.py
# 资产证据链：来源单元 → 文章 asset:// → 成品 assets（assetId 文件名）→ 相对 sourceAssetRef 可回查
python3 quwoquan_data/tests/local_contract/common/test_source_unit_evidence_chain__local_contract_test.py
# 目录与资产静态门 + 文风门：散落 images/、绝对路径、机械收尾标题、无类别 weather 来源全阻断
python3 quwoquan_data/tests/local_contract/verify/test_directory_evidence_gate__local_contract_test.py
# 图片下载 6 门：相关性必填非模板、每实体≥2、最小像素、contentType+版权持久化、多变体(webp)、感知去重
python3 quwoquan_data/tests/local_contract/download/test_image_download_gates__local_contract_test.py
# RC3 图文混排：HTML 内联<img>就地同源捕获(抽取器分发/相对解析/data:跳过/payload清单)
# + 内联候选构建与五道硬门后回连段落占位(同源不绕许可)
python3 quwoquan_data/tests/local_contract/download/test_fetch_registry_dispatch__local_contract_test.py
python3 quwoquan_data/tests/local_contract/download/test_inline_source_images__local_contract_test.py
# P2 连续图组（figuregroup）回填契约：expand 回填/带回完整性/绑定后清理/计数/净化保结构
python3 quwoquan_data/tests/local_contract/common/test_figure_group_backfill__local_contract_test.py
# P3 三类解耦：实体主页主源【只限百科】+ 文章【含内联视频则放弃】检测 + hasVideo 持久化
python3 quwoquan_data/tests/local_contract/common/test_three_class_decouple__local_contract_test.py
# P4 图库合规：图虫/Pinterest 受限如实标注+替代路径+授权完整性硬门+非中文译简体门
python3 quwoquan_data/tests/local_contract/common/test_image_provider_compliance__local_contract_test.py
# P5 字数门自适应 + 软门统一口径：review/verify 同源消除第二真相源 + 非致命检查降软扣分
python3 quwoquan_data/tests/local_contract/common/test_soft_gate_unification__local_contract_test.py
# P6 无人托管可靠性：错峰冷启释放器+per-worker warm bridge+冷启并发上限+吞吐/connection-refused 量化+cloud orchestrator 硬超时看门狗
python3 quwoquan_data/tests/local_contract/task/test_unattended_reliability__local_contract_test.py
# 并发横向扩展：bridge 启动锁 per-workspace（解多 clone 全局串行）+ throughput-plan 确定性容量推算（十万级量化）
"$PYTEST_RUNNER" -m pytest -q quwoquan_data/tests/local_contract/task/test_throughput_scaling__local_contract_test.py
# 标签可点击态：tag 本体保持语义定义，link target 由 publish index 派生
python3 quwoquan_data/tests/local_contract/publish/test_tag_link_targets__local_contract_test.py
# 覆盖账本：coverage/{省}.ndjson 派生（主清单×publish×env_releases）+ 跨省 isPrimary + 主页路由绑定
python3 quwoquan_data/tests/local_contract/publish/test_coverage_index__local_contract_test.py
# 行政区标签层级：V1 中国两级选择依赖 34 省级、广东完整地级市、北京区县 direct children
python3 quwoquan_data/tests/local_contract/publish/test_admin_region_tags__local_contract_test.py
# 结构化出处：5.review/provenance.json 统一回查入口（agent 输入/最终结果/原始源/证据源/门结果）+ 强制完整性/一致性门
python3 quwoquan_data/tests/local_contract/common/test_provenance__local_contract_test.py
# 实体标注：词典 grounding + inline 机械标注（首次出现/frontmatter 安全）+ ref 闭环强校验 + 发布强制覆盖门
python3 quwoquan_data/tests/local_contract/common/test_entity_annotation__local_contract_test.py
# 「明」交集信号：intersectionHints 对齐 IntersectionReason 闭集/字段 + 维度完备性 + 锚点闭环门
python3 quwoquan_data/tests/local_contract/common/test_intersection_signal__local_contract_test.py
# 单会话多实体批处理：批 prompt 打包 N 实体（聚合 writing_pack + 跨篇多样性约束）+ 完整性/完成度
python3 quwoquan_data/tests/local_contract/common/test_batch_orchestration__local_contract_test.py
# Fan-out 编排脚手架：计划构建/去重/互斥/覆盖/冻结门
python3 quwoquan_data/tests/local_contract/orchestrate/test_fanout_plan__local_contract_test.py
# Fan-out 四策略展开（by-partition / flat-pool / by-leaf / by-batch）确定性 + 不变量
python3 quwoquan_data/tests/local_contract/orchestrate/test_fanout_strategies__local_contract_test.py
# Fan-out 调度：冻结门 + 建 task/batch + 入队叶子 + 幂等可重放 + rollup 聚合
python3 quwoquan_data/tests/local_contract/orchestrate/test_fanout_dispatch__local_contract_test.py
# Fan-out 退化等价：--mode fanout --concurrency 1 --strategy flat-pool 与 single 同终态
python3 quwoquan_data/tests/local_contract/orchestrate/test_mode_single_fanout_equivalence__local_contract_test.py
# Fan-out 外部 runner（mock SDK）：lease→complete 回写、startup vs run 失败分流、用量/预算门
python3 quwoquan_data/tests/local_contract/orchestrate/test_fanout_runner__local_contract_test.py
# 百科多层目录 + 章节配图 + 对象阶段树 + wikitext 锚点（新批次验收）
python3 quwoquan_data/tests/local_contract/common/test_section_outline_and_placement__local_contract_test.py
python3 quwoquan_data/tests/local_contract/common/test_object_stages_and_wikitext__local_contract_test.py
# 底稿忠实重构 + 无人托管可靠性（P0 探针分类、key 单一真相源、scaled-e2e 续跑、
# RC2/RC4/RC6 同源硬门、形态自适应字数门、实体聚焦、多地点 route 死代码收口）
"$PYTEST_RUNNER" -m pytest -q \
  quwoquan_data/tests/local_contract/env/test_cursor_probe__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_cursor_credentials__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_scaled_e2e_run__local_contract_test.py \
  quwoquan_data/tests/local_contract/task/test_task_input_contract__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_output_root_isolation__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_batch_shared_evidence_slim__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_artifacts_index__local_contract_test.py \
  quwoquan_data/tests/local_contract/verify/test_output_root_isolation_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_adaptive_word_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/common/test_entity_focus__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_source_quality_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_homepage_source_judge__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_image_collection_gate__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_source_plan_registry_guidance__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_auto_research_article_homepage__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_auto_research_image_lane__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_auto_research_transport__local_contract_test.py \
  quwoquan_data/tests/local_contract/download/test_entity_homepage_image_wikitext_truth_source__local_contract_test.py \
  quwoquan_data/tests/local_contract/produce/test_route_assets_layout__local_contract_test.py

echo "[verify-quwoquan-data] PASSED"
