# 阶段证据：三类解耦——route 单一多目的地底稿模型 + 门禁接线

任务节点：`fix-3class-routing`（含 route 单一多目的地底稿模型，修 route_brief）
绑定特性树：AppRoot 内容工厂 → L1 数据工程(quwoquan_data) → L2 底稿中心内容生产 →
L3 线路文章三类解耦 / 单一多目的地底稿
验收意图：contract（local_contract）
测试证据层：`local_contract`

## 根因

RC4 同源硬门把文章配图收窄为「只从单一 `brief.baseSourceRef` 底稿来源取图」。但
`_build_route_assets` **同时被单实体文章（entity_workflow）与多目的地线路（route_compose）复用**：

- 线路 brief 天然多目的地、无单一 `baseSourceRef`（routeNodes 各有各的来源），
  RC4 后 `base_pool` 恒空 → `pack["assets"] == []` →
  `test_route_workflow_generates_real_review_green` 失败（且空资产触发修复重跑，整文件 109s）。

线路与「只能来自一个底稿」并不矛盾：线路是**多目的地**叙事，每个目的地节点本身是
单一来源单元（节点内不跨源、节点间不互借），这正是用户单列的「route 单一多目的地底稿模型」。

## 改动（仅 `quwoquan_data/**`，加性、不回归单实体路径）

`quwoquan_data/scripts/_common/content_evidence.py`：

- `build_route_evidence_bundle` 为每个 route 节点新增 `baseSourceId` / `baseSourceUrl`：
  在该节点保留源中按 `assessment.score` 择优，取最佳单一来源作节点底稿（无保留源 ⇒ 空，
  该节点文字承载）。

`quwoquan_data/scripts/produce/route_assets.py`：

- 新增 `_node_base_pool(candidates, base_source_id)`：某目的地节点的同源候选 =
  `researchLane!=image` 且 `Path(sourceRef).parent.name == baseSourceId`（来源单元 == 节点底稿）。
- 新增 `_build_multi_destination_route_assets(...)`：cover←首节点底稿、各 node←本节点底稿、
  closing←末节点底稿；节点内不跨源、节点间不互借；某节点无可用同源图 ⇒ 该节点文字承载。
- `_build_route_assets` 增加分支：**仅当无单一 `baseSourceRef` 且 `>=2` 目的地节点**（多目的地
  线路）走 per-node；单实体文章 / 已声明单一底稿仍走原单一 `base_pool`（保留既有同源硬门，
  不回归）。

`quwoquan_data/scripts/verify/verify_quwoquan_data.sh`：

- 在 `test_entity_composer.py` 后接入 `test_route_brief_and_evidence.py`（pytest 跑全 8 例）。

## 关键边界（避免回归）

- 单实体文章：`entity_names` 只有 1 个 ⇒ 不进 per-node 分支 ⇒ 原单一 `base_pool` 行为不变。
- 已声明单一底稿的线路：`base_source_ref` 非空 ⇒ 不进 per-node 分支 ⇒ 原行为不变。
- per-node 选图复用既有 `_pick_safe_image`（全局 `chosen` 去重 + 跳过 unsafe），节点间图片不重复。

## 验证结果（系统 venv python）

- `test_route_brief_and_evidence.py`：8 passed（修复前 1 failed / 整文件 109.7s；修复后 6.86s）。
- 单独跑此前失败用例 `test_route_workflow_generates_real_review_green`：passed（4.4s）。
- `test_entity_composer.py`（门禁内，单实体路径）：7 passed，无回归。
- `test_route_assets_layout__local_contract_test.py`（门禁内）：5 passed。
- 整个 `quwoquan_data/tests/produce/`：101 passed。
- 门禁新增命令原样执行：8 passed，gate_exit=0。

## 剩余（fix-3class-routing 后续）

- 线路 `sourceUrls` / `sourcePaths` 收敛为「N 个节点底稿」而非全部来源（用户投诉 #6 的 route 侧
  简化），作为后续独立小步（避免与本步资产模型耦合放大风险）。
- 实体=百科择优单源（fix-entity-baike-best）。
- download fetch 物理目录仍按实体键控（消费层物理重构）。
