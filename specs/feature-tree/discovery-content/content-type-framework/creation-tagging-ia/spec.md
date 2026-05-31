# L3 Scenario: creation-tagging-ia

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `content-type-framework`
- `L3_story`: `creation-tagging-ia`

本场景冻结**创作侧打标信息架构（IA）**：在内容创作流提供 tagRef 打标入口，使 `content.tagRefs` 成为「交集」归因的可信输入。打标对全部内容类型（含口碑 review）**可选、不强制**，由**自动打标（转发识别 + 内容识别）辅助**，手动 UI 作为对自动结果的**确认/修正层**。打标真相源唯一为数据工程 `publish/v1/tags`（路径制 tagRef）；首发标签子集已冻结于 `_shared/tag_ref_migration.yaml` 的 `launch` 项。

## 背景与动机

「交集」是产品北极星：用户因共同的地点/事物/标签连接。`Post.tagRefs`（路径制 tagRef，E4 已硬切）+ `entityRefs`（POI）是交集召回与归因的核心输入。当前创作流（`create_page` / 各类型编辑页）**无打标入口**——`CreatePost.writable_fields` 已支持 `tagRefs`（payload 通道就绪），但端侧无 UI 注入，导致用户内容 `tagRefs` 长期为空、交集稀疏、归因链断裂。

口碑（review，B1/C1）进一步放大这一缺口：口碑天然需要"地点 + 维度（旅行/摄影/美食…）"标签。因此创作打标 IA 是口碑与交集呈现的硬前置之一。

## 目标用户与核心问题

- **创作者**：发布内容时以最低摩擦标注主题/维度，让内容被同好/同地/同事物的人看到。
- **核心问题**：在不增加发布负担的前提下，让 `content.tagRefs` 被有效填充且噪声可控，使「打标 → content.tagRefs → 交集归因」可还原。

## 范围（In Scope）

### F1. 打标可选（全类型，无强制门槛）— 冻结
- 图文（image/video/article）、微趣（micro）、口碑（review）创作均**可选打标**；发布不因缺标签被拦截。
- 不引入"发布前至少 N 标签"硬门槛；标签密度由自动打标 + 推荐芯片自然提升。

### F2. 入口：各类型编辑页内联打标区 — 冻结
- 打标区**内联在各类型编辑页**（图文/视频/口碑编辑页内），与既有发布前选择器（location/circle 独立页）形态区分：打标是编辑态内联、低摩擦勾选，不单开一页。
- 口碑编辑页的打标区与 POI 选择联动（POI 自动带出地点维度建议）。

### F3. 自动打标辅助（确认/修正层）— 冻结 IA 契约
- 创作页消费**自动打标建议** `suggestedTagRefs`（来源：转发识别 reshare-derived + 内容识别 content-recognition）。
- 自动建议以**可编辑/可删除芯片**呈现；用户一键勾选/取消/删除，避免错误标签进入交集召回。
- 自动打标的模型/管线（ML/数据工程）**不在本场景**；本场景只冻结端侧消费 `suggestedTagRefs` 的 IA 契约与可修正语义。

### F4. 交互形态：推荐芯片 + 搜索补充（分阶段）— 冻结
- **首发态（C2 `publish/v1/tags` 未发布）**：UI = `首发 launch 子集芯片` + `自动建议芯片` 多选，上限 5；纯勾选零输入，不依赖 C2 全量检索。
- **目标态（C2 发布后灰度开启）**：芯片下方「搜索更多标签」入口，检索源 `publish/v1/tags` 全量树，覆盖 deferred 长尾垂类；以 feature flag 灰度。

### F5. 首发标签子集 — 引用既有冻结
- 首发子集唯一来源为 `_shared/tag_ref_migration.yaml` 的 `status: launch` 项：`Topic/旅行`、`Topic/摄影`、`Topic/美食餐饮`、`Topic/地理`、`Entity/地点`、`Entity/机构`、`Format/内容载体`（校园 + 旅游尖刀）。
- 不在端侧另建第二套标签列表；芯片集合从该子集 + 自动建议派生。

### F6. payload 注入与归因可还原 — 冻结
- 选定 tagRefs 经 `CreatePost`/`UpdatePost`（draft）的 `writable_fields.tagRefs` 注入（已通）。
- 验收口径：发布后 `content.tagRefs` 含用户选定 + 已确认的自动标签；该 tagRefs 进入推荐召回与 `IntersectionReason` 归因，使「打标 → content.tagRefs → 交集」可还原。

## 验收映射（A1~An → T1~T4）

| 验收 | 描述 | 证据层 |
|---|---|---|
| A1 | 各类型编辑页有内联打标区；打标可选，缺标签不拦截发布 | T2 widget |
| A2 | 芯片集合来自首发 launch 子集 + 自动建议 `suggestedTagRefs`，多选上限 5 | T2 widget |
| A3 | 自动建议芯片可勾选/取消/删除，修正后 tagRefs 正确 | T2 widget |
| A4 | 选定 tagRefs 经 CreatePost 注入，发布后 content.tagRefs 一致 | T1 契约 + T2 |
| A5 | tagRefs 进召回与 IntersectionReason，打标→交集归因可还原 | T2 + T3 |
| A6 | 搜索补充在 C2 后由 flag 灰度开启，检索源唯一为 publish/v1/tags | T2（flag 关时不渲染） |

## SLO / KPI

| 指标 | 门槛 |
|---|---|
| 打标区渲染 TTI | ≤ 编辑页首屏预算内（不阻塞编辑） |
| 自动建议拉取超时降级 | 超时则只显首发子集芯片，不阻断发布 |
| 发布内容带 ≥1 tagRef 比例（首发尖刀垂类） | 运营观测 KPI（非硬门槛） |

## 权限边界与数据生命周期

- 打标随内容生命周期：draft 可改 tagRefs，published 不可变（与既有内容一致）。
- 自动建议为辅助态，未经用户确认不得静默写入 published 内容的 tagRefs（避免不可控归因）。
- tagRef 真相源唯一为 `publish/v1/tags`；端侧不持久化第二套标签字典。

## 迁移 / 灰度 / 回滚

- 纯增量端侧能力（编辑页加打标区），不改写链路契约（payload 已通）。
- 灰度：打标区曝光 + 搜索补充各自 flag；自动建议拉取失败安全降级到首发子集芯片。
- 回滚：关闭打标区 flag 即回到无打标态，content.tagRefs 退化为空（与现状一致），无数据损失。

## Out of Scope

- 自动打标模型/管线（转发识别、内容识别）的实现——属 ML/数据工程；本场景只冻结消费 `suggestedTagRefs` 的 IA 契约。
- `publish/v1/tags` 真相源的发布——属 C2（数据工程）。
- 标签运营后台、标签合并/治理。
- pageflip 受控文件。

## 约束

- tagRef 唯一真相源 `publish/v1/tags`（路径制，以 `Topic/Audience/Format/Entity` 开头，`verify_tag_tree.py` R10）；首发子集只引用 `tag_ref_migration` 的 `launch` 项，不另立第二套。
- payload 注入复用 `CreatePost.writable_fields.tagRefs`，不新增端点、不硬编码 path/operation/surface（01-arch-constraints §2.2.1）。
- 遵循 13-coding-discipline：R06 元数据驱动、R15 Mock 隔离（标签 mock 走 Repository/fixture）、R20 创作页埋点（打标曝光/选择/自动建议确认）。

## 验收重点

1. 各类型编辑页内联打标区已落，打标可选、不拦截发布。
2. 芯片集合来自首发 launch 子集 + 自动建议，多选 ≤5，自动建议可修正。
3. 选定 tagRefs 经 CreatePost 注入，发布后 content.tagRefs 一致。
4. tagRefs 进召回与交集归因，"打标 → content.tagRefs → 交集"可还原。
5. 搜索补充由 flag 灰度（C2 后），检索源唯一 publish/v1/tags。

## 设计决策（冻结）

> L3 故事的 design 细节并入本 spec（feature-tree 约定 L3 仅 `spec.md`+`acceptance.yaml`）。

### B3-D1 打标可选
全类型可选、不设强制门槛；标签密度靠自动打标 + 推荐芯片自然提升，而非发布拦截。

### B3-D2 入口形态
内联各类型编辑页（区别于 location/circle 的独立发布前选择页）；口碑编辑页打标区与 POI 选择联动。

### B3-D3 自动打标辅助
端侧消费 `suggestedTagRefs`（reshare-derived + content-recognition），以可编辑/可删除芯片呈现作为确认/修正层；模型/管线属 ML，本场景只冻结 IA 契约与"未确认不静默写入"语义。

### B3-D4 交互形态（分阶段，推荐态）
- 首发：`launch 子集芯片` + `自动建议芯片` 多选 ≤5，零输入，不依赖 C2。
- 目标：C2 后 flag 灰度「搜索更多标签」，检索源 `publish/v1/tags` 全量树覆盖 deferred 长尾。
- 取舍：相比单选垂类根（覆盖低、承不住自动多标签）与纯芯片无搜索（长尾覆盖不足），分阶段方案兼顾首发零依赖与目标态高覆盖。

### B3-D5 首发标签子集
唯一来源 `_shared/tag_ref_migration.yaml` `launch` 项（校园 + 旅游尖刀 7 个垂类根 + Format/内容载体），端侧不另建标签列表。

### B3-D6 payload 注入与归因
tagRefs 经 `CreatePost`/`UpdatePost` 注入（已通）；验收以"发布后 content.tagRefs 一致 + 进召回/IntersectionReason"为准。

### B3-D7 实施顺序（slices：metadata 复用 → 端侧 IA → 测试）
1. 复用既有 metadata（tagRefs 字段 + writable_fields 已就绪，无 metadata 增量；若需 `suggestedTagRefs` 读契约再 metadata-first 增量）。
2. 端侧：编辑页内联打标区（芯片多选 ≤5）+ 自动建议消费 + Repository/fixture 标签源（Mock 隔离）。
3. 灰度 flag：打标区曝光 + 搜索补充。
4. 测试：T1 payload 注入契约 / T2 打标 widget（可选/上限/修正/降级）/ T3 召回与交集归因。
