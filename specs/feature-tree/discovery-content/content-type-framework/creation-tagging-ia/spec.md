# L3 Scenario: creation-tagging-ia

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `content-type-framework`
- `L3_story`: `creation-tagging-ia`

本场景冻结**创作侧打标信息架构（IA）**：在内容创作流提供 tagRef 打标入口，使 `content.tagRefs` 成为「交集」归因的可信输入。打标对全部内容类型（image/video/article/micro）**可选、不强制**，由**自动打标（转发识别 + 内容识别）辅助**，手动 UI 作为对自动结果的**确认/修正层**。打标真相源唯一为数据工程 `control_plane/governance/taxonomy`（路径制 tagRef）；端侧只通过 tag-service serving projection 查询，不维护静态子集。

## 背景与动机

「交集」是产品北极星：用户因共同的地点/事物/标签连接。`Post.tagRefs`（路径制 tagRef，E4 已硬切）+ `entityRefs`（POI）是交集召回与归因的核心输入。当前创作流（`create_page` / 各类型编辑页）**无打标入口**——`CreatePost.writable_fields` 已支持 `tagRefs`（payload 通道就绪），但端侧无 UI 注入，导致用户内容 `tagRefs` 长期为空、交集稀疏、归因链断裂。

带地点/事物的内容（如绑定 POI 的图文）尤其需要"地点 + 维度（旅行/摄影/美食…）"标签。因此创作打标 IA 是交集呈现的硬前置之一。

## 目标用户与核心问题

- **创作者**：发布内容时以最低摩擦标注主题/维度，让内容被同好/同地/同事物的人看到。
- **核心问题**：在不增加发布负担的前提下，让 `content.tagRefs` 被有效填充且噪声可控，使「打标 → content.tagRefs → 交集归因」可还原。

## 范围（In Scope）

### F1. 打标可选（全类型，无强制门槛）— 冻结
- 图文（image/video/article）、微趣（micro）创作均**可选打标**；发布不因缺标签被拦截。
- 不引入"发布前至少 N 标签"硬门槛；标签密度由自动打标 + 推荐芯片自然提升。

### F2. 入口：各类型编辑页内联打标区 — 冻结
- 打标区**内联在各类型编辑页**（图文/视频编辑页内），与既有发布前选择器（location/circle 独立页）形态区分：打标是编辑态内联、低摩擦勾选，不单开一页。
- 绑定 POI 的内容编辑页打标区与 POI 选择联动（POI 自动带出地点维度建议）。

### F3. 自动打标辅助（确认/修正层）— 冻结 IA 契约
- 创作页消费**自动打标建议** `suggestedTagRefs`（来源：转发识别 reshare-derived + 内容识别 content-recognition）。
- 自动建议以**可编辑/可删除芯片**呈现；用户一键勾选/取消/删除，避免错误标签进入交集召回。
- 自动打标的模型/管线（ML/数据工程）**不在本场景**；本场景只冻结端侧消费 `suggestedTagRefs` 的 IA 契约与可修正语义。

### F4. 交互形态：推荐芯片 + 搜索补充 — 冻结
- UI 展示 tag-service 返回的常用标签与 `自动建议芯片`，多选上限 5；端侧不内置标签 catalog。
- 芯片下方「搜索更多标签」入口查询 tag-service serving projection；功能开关只控制入口曝光，不改变标签真相源。

### F5. 标签查询边界 — 冻结
- 常用标签、搜索结果和自动建议必须返回可由 tag-service 解析的 tagRef。
- 不在端侧另建第二套标签列表；离线态只展示本次草稿已选标签，不伪造 catalog。

### F6. payload 注入与归因可还原 — 冻结
- 选定 tagRefs 经 `CreatePost`/`UpdatePost`（draft）的 `writable_fields.tagRefs` 注入（已通）。
- 验收口径：发布后 `content.tagRefs` 含用户选定 + 已确认的自动标签；该 tagRefs 进入推荐召回与 `IntersectionReason` 归因，使「打标 → content.tagRefs → 交集」可还原。

## 验收映射（A1~An → 三层测试）

| 验收 | 描述 | 证据层 |
|---|---|---|
| A1 | 各类型编辑页有内联打标区；打标可选，缺标签不拦截发布 | local_contract widget |
| A2 | 芯片集合来自 tag-service 查询 + 自动建议 `suggestedTagRefs`，多选上限 5 | local_contract widget |
| A3 | 自动建议芯片可勾选/取消/删除，修正后 tagRefs 正确 | local_contract widget |
| A4 | 选定 tagRefs 经 CreatePost 注入，发布后 content.tagRefs 一致 | local_contract 契约 + local_contract |
| A5 | tagRefs 进召回与 IntersectionReason，打标→交集归因可还原 | local_contract + api_integration |
| A6 | 搜索补充由 flag 控制入口曝光，查询源唯一为 tag-service serving projection | local_contract（flag 关时不渲染） |

## SLO / KPI

| 指标 | 门槛 |
|---|---|
| 打标区渲染 TTI | ≤ 编辑页首屏预算内（不阻塞编辑） |
| 自动建议拉取超时降级 | 超时则保留已选标签，不阻断发布，不伪造标签 catalog |
| 发布内容带 ≥1 tagRef 比例（首发尖刀垂类） | 运营观测 KPI（非硬门槛） |

## 权限边界与数据生命周期

- 打标随内容生命周期：draft 可改 tagRefs，published 不可变（与既有内容一致）。
- 自动建议为辅助态，未经用户确认不得静默写入 published 内容的 tagRefs（避免不可控归因）。
- tagRef 真相源唯一为 `control_plane/governance/taxonomy`；端侧不持久化第二套标签字典。

## 迁移 / 灰度 / 回滚

- 纯增量端侧能力（编辑页加打标区），不改写链路契约（payload 已通）。
- 灰度：打标区曝光 + 搜索补充各自 flag；自动建议拉取失败时保留已选标签并允许无标签发布。
- 回滚：关闭打标区 flag 即回到无打标态，content.tagRefs 退化为空（与现状一致），无数据损失。

## Out of Scope

- 自动打标模型/管线（转发识别、内容识别）的实现——属 ML/数据工程；本场景只冻结消费 `suggestedTagRefs` 的 IA 契约。
- taxonomy 的治理与发布导入——属数据工程与 tag-service。
- 标签运营后台、标签合并/治理。
- pageflip 受控文件。

## 约束

- tagRef 唯一真相源 `control_plane/governance/taxonomy`（路径制，以 `Topic/Audience/Format/Entity` 开头）；端侧只消费 tag-service serving projection，不另立第二套。
- payload 注入复用 `CreatePost.writable_fields.tagRefs`，不新增端点、不硬编码 path/operation/surface（01-arch-constraints §2.2.1）。
- 遵循 13-coding-discipline：R06 元数据驱动、R15 Mock 隔离（标签 mock 走 Repository/fixture）、R20 创作页埋点（打标曝光/选择/自动建议确认）。

## 验收重点

1. 各类型编辑页内联打标区已落，打标可选、不拦截发布。
2. 芯片集合来自 tag-service 查询 + 自动建议，多选 ≤5，自动建议可修正。
3. 选定 tagRefs 经 CreatePost 注入，发布后 content.tagRefs 一致。
4. tagRefs 进召回与交集归因，"打标 → content.tagRefs → 交集"可还原。
5. 搜索补充由 flag 控制曝光，查询源唯一为 tag-service serving projection。

## 设计决策（冻结）

> L3 故事的 design 细节并入本 spec（feature-tree 约定 L3 仅 `spec.md`+`acceptance.yaml`）。

### B3-D1 打标可选
全类型可选、不设强制门槛；标签密度靠自动打标 + 推荐芯片自然提升，而非发布拦截。

### B3-D2 入口形态
内联各类型编辑页（区别于 location/circle 的独立发布前选择页）；绑定 POI 的内容编辑页打标区与 POI 选择联动。

### B3-D3 自动打标辅助
端侧消费 `suggestedTagRefs`（reshare-derived + content-recognition），以可编辑/可删除芯片呈现作为确认/修正层；模型/管线属 ML，本场景只冻结 IA 契约与"未确认不静默写入"语义。

### B3-D4 交互形态
- tag-service 常用标签 + `自动建议芯片` 多选 ≤5；搜索入口由 flag 控制。
- 取舍：统一查询 serving projection，避免端侧首发子集与全量 taxonomy 形成双真相源。

### B3-D5 标签来源
常用标签和搜索结果只由 tag-service 返回，端侧不另建标签列表。

### B3-D6 payload 注入与归因
tagRefs 经 `CreatePost`/`UpdatePost` 注入（已通）；验收以"发布后 content.tagRefs 一致 + 进召回/IntersectionReason"为准。

### B3-D7 实施顺序（slices：metadata 复用 → 端侧 IA → 测试）
1. 复用既有 metadata（tagRefs 字段 + writable_fields 已就绪，无 metadata 增量；若需 `suggestedTagRefs` 读契约再 metadata-first 增量）。
2. 端侧：编辑页内联打标区（芯片多选 ≤5）+ 自动建议消费 + Repository/fixture 标签源（Mock 隔离）。
3. 灰度 flag：打标区曝光 + 搜索补充。
4. 测试：local_contract payload 注入契约 / local_contract 打标 widget（可选/上限/修正/降级）/ api_integration 召回与交集归因。
