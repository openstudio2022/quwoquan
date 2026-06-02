#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

# CLI-first ratchet：拦截新增直跑业务入口脚本（必须经 qwq-data 暴露给 skill）
python3 quwoquan_data/scripts/verify/verify_cli_first.py
# 契约门：会话 agent = 唯一模型执行者（禁外部 LLM SDK/端点 + 交付正文 agent-only 防线）
python3 quwoquan_data/tests/test_agent_executor_contract.py
python3 quwoquan_data/scripts/cli.py template lint
python3 quwoquan_data/scripts/cli.py template creator-lint
python3 quwoquan_data/scripts/cli.py template rec-contract
python3 quwoquan_data/scripts/cli.py template region-season-lint
# 收紧扫描范围：只校验当前 schema 的 posts 根（旧遗留包通过 --scope all 单独审计）
python3 quwoquan_data/scripts/cli.py verify --scope current
# 任务工程：committed 任务规格校验（路径↔id、archetype scope、实体类型真相源、重复）
python3 quwoquan_data/scripts/cli.py task lint
# 任务工程 + 采样回填契约测试
python3 quwoquan_data/tests/test_task_cli.py
python3 quwoquan_data/tests/test_ship_sampling.py
# Phase 0：sop few-shot 注入 + download 预置 source_plan 可消费（默认零源 bug 回归）
python3 quwoquan_data/tests/test_sop_injection.py
python3 quwoquan_data/tests/test_download_source_plan.py
# Phase 1：download 真实下图（sniff/curated/fetch_image/handler 接线）
python3 quwoquan_data/tests/test_download_images.py
# Phase 1：build 实体主页真实链路（prepare 下发契约 + validate 采纳门）
python3 quwoquan_data/tests/test_build_homepage.py
# Phase 1：实体 composer 红绿契约 + entityRef 全路径回归（发布门主实体不被误过滤）
python3 quwoquan_data/tests/test_entity_composer.py
# 内容质量：asset:// 引用闭环（引用↔manifest↔fileName↔物理文件↔sha256）+ assetId 可读化 + gallery caption 语义化
python3 quwoquan_data/tests/test_asset_refs.py
# 源覆盖：旅游/校园源类别注册表归类 + 源类别覆盖门（「全」）+ catalog 结构 lint
python3 quwoquan_data/tests/test_source_catalog.py
# 文风开篇：styleFamily 多开篇策略自选 + 按所选族语义化检测 + 开篇引导下发 + catalog 结构 lint
python3 quwoquan_data/tests/test_style_catalog.py
# 文风门：开篇钩子语义化（按所选 styleFamily/openingStrategy）+ 跨篇相似度门（破量产千篇一律）
python3 quwoquan_data/tests/test_style_gates.py
# 文章目录：posts/<type>/<发布标题>/<seq>/（标题在 article 之下、序号默认 1、标题重复递增、与 promote 对齐）
python3 quwoquan_data/tests/test_post_dir_layout.py
# 结构化出处：provenance.json 统一回查入口（agent 输入/最终结果/原始源/证据源/门结果）+ 强制完整性/一致性门
python3 quwoquan_data/tests/test_provenance.py
# 实体标注：词典 grounding + inline 机械标注（首次出现/frontmatter 安全）+ ref 闭环强校验 + 发布强制覆盖门
python3 quwoquan_data/tests/test_entity_annotation.py
# 「明」交集信号：intersectionHints 对齐 IntersectionReason 闭集/字段 + 维度完备性 + 锚点闭环门
python3 quwoquan_data/tests/test_intersection_signal.py
# 单会话多实体批处理：批 prompt 打包 N 实体（聚合 writing_pack + 跨篇多样性约束）+ 完整性/完成度
python3 quwoquan_data/tests/test_batch_orchestration.py

echo "[verify-quwoquan-data] PASSED"
