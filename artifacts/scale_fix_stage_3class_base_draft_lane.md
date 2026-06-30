# 阶段证据：三类解耦——底稿认领按内容类型路由各自来源（base_draft lane 前移）

任务节点：`fix-3class-routing`（实体/文章/图片三类 download 按内容类型路由各自来源）
绑定特性树：AppRoot 内容工厂 → L1 数据工程(quwoquan_data) → L2 底稿中心内容生产 → L3 三类彻底解耦各自来源
验收意图：contract（local_contract）
测试证据层：`local_contract`

## 背景与根因

子代理勘察结论：来源「发现层」（research-plan）已按内容类型（lane）解耦，但「消费层」仍按
实体目录物理键控，`researchLane` 仅作标签。最关键的跨类型污染发生在
`_common/base_draft.py::base_draft_candidates` / `assign_base_draft`：它们遍历一个实体目录下
**全部**来源单元（不分 researchLane），仅按质量分择优，导致：

- 文章载体可能误把「百科主页源」或「图库集合源」选为底稿；
- 图片作品载体可能误把「游记文章源」选为底稿。

此前唯一兜底是下游 `content_plan.py` 的 researchLane 门（晚拦截）。本子步把「按内容类型选取
各自来源」**前移到底稿认领源头**，源头杜绝跨类型误选。

## 改动（仅 `quwoquan_data/**`，零下游行为回归）

`quwoquan_data/scripts/_common/base_draft.py`：

- 新增 `_CARRIER_BASE_DRAFT_LANES` 映射与 `base_draft_allowed_lanes(carrier)`：
  - `article` / `route` / `review` → `{"article","legacy",""}`
  - `gallery` / `image` → `{"image"}`
  - `homepage` / `entity` → `{"homepage","encyclopedia","legacy",""}`
  - 未知 / 未声明载体 → `None`（不限制，兼容旧 brief 与 homepage 直连路径）
  - 兼容期空标签 `""` 视为历史通用底稿，与 content_plan 的 researchLane 门口径一致。
- 新增 `_unit_research_lane(unit_dir)` 读取来源单元 `meta.json.researchLane`。
- `base_draft_candidates` 的候选行新增 `researchLane` 字段（无副作用的附加字段）。
- `assign_base_draft`（**produce 认领路径**）按 `brief.carrier`（兼容 `contentType`、`gallery→image`）
  收窄候选到对应 lane；未知载体不过滤。

关键边界（避免回归）：

- `build/homepage.py` 用**无 carrier** 的 brief 直接调 `base_draft_candidates`，且自身用
  `homepage_base_draft_readiness` 做百科 lane 过滤 —— 本子步**只改 `assign_base_draft`**，
  `base_draft_candidates` 默认行为不变，homepage 路径不受影响。
- 声明的 `baseSourceRef` 若指向错 lane 来源，会被收窄到正确 lane 后改派（不原样透传）。

## 测试（已在门禁，line 52）

`quwoquan_data/tests/local_contract/common/test_base_draft_fidelity__local_contract_test.py` 新增 4 例：

- `test_base_draft_allowed_lanes_decouples_by_carrier`：载体→lane 映射与未知载体不限制。
- `test_assign_base_draft_article_carrier_excludes_image_lane_source`：image lane 质量分更高
  （9>7）仍被文章载体排除，落到 article lane。
- `test_assign_base_draft_gallery_carrier_excludes_article_lane_source`：article lane 质量分更高
  （9>6）仍被图片作品载体排除，落到 image lane。
- `test_assign_base_draft_declared_wrong_lane_ref_is_reassigned_to_correct_lane`：声明错 lane ref
  被改派到正确 lane。

## 验证结果（系统 venv python）

- 本文件 15 passed（11 旧 + 4 新）。
- 门禁原样组合（base_draft_fidelity + content_plan_distribution + content_plan_source_gate）：28 passed。
- 门禁原样组合（homepage_prepare + auto_content_plan + content_plan_source_contract +
  task_author_review + download_auto_research）：61 passed。
- entity composer（门禁内）：7 passed，无回归。
- `tests/common/test_batch_asset_registry.py` / `test_batch_asset_stability.py` 按门禁独立进程：全 PASS
  （pytest 同会话共享 QWQ_RUNTIME_ROOT 的 3 例失败为预存在跨文件污染，与本改动无关）。

## 剩余（仍属 fix-3class-routing / 后续节点）

- route 单一多目的地底稿模型（route_brief 非门禁，待后续 route 模型修复）。
- 实体=百科择优单源（fix-entity-baike-best）。
- download fetch 物理目录仍按实体键控（消费层物理重构）——本子步先在底稿认领语义层完成解耦。
