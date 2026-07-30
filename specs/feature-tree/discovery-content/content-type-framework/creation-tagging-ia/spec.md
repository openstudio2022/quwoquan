# L3 Story：创作打标信息架构 (`creation-tagging-ia`)

> 所属能力：[`content-type-framework`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望冻结创作侧打标 IA：各类型编辑页内联打标区，打标全类型可选、不强制，由自动打标（转发识别+内容识别）辅助，手动 UI 作确认/修正层，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- 各类型编辑页内联打标区（图文/视频），打标可选不拦截发布
- 自动打标建议 suggestedTagRefs 消费 + 可编辑/可删除芯片（确认/修正层）
- 交互形态：tag-service 常用标签 + 自动建议多选 ≤5；搜索入口由 flag 控制
- 端侧不维护标签 catalog 或首发子集
- tagRefs 仅由 CreatePost/UpdatePost request entity 中的 semanticMentions 派生（已通）

### Out of Scope

- 自动打标模型/管线（转发识别、内容识别）实现（属 ML/数据工程）
- taxonomy 治理与发布导入（属数据工程与 tag-service）
- 标签运营后台/治理
- pageflip 受控文件

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 各类型编辑页内联打标区，打标可选不拦截发布

- 各类型编辑页必须提供可选的内联打标区，用户不选择标签时仍可发布。

<a id="req-002"></a>
### REQ-002 芯片集来自首发 launch 子集 + 自动建议，多选上限 5

- 标签芯片只能来自 launch 子集与自动建议，用户最多选择 5 个。

<a id="req-003"></a>
### REQ-003 自动建议芯片可勾选/取消/删除，修正后 tagRefs 正确

- 用户可勾选、取消或删除自动建议，最终提交的 `tagRefs` 必须反映用户确认后的选择。

<a id="req-004"></a>
### REQ-004 选定 tagRefs 经 CreatePost 注入，发布后 content.tagRefs 一致

- `CreatePost` 必须携带用户确认的 `tagRefs`，发布后的内容投影必须保持一致。

<a id="req-005"></a>
### REQ-005 tagRefs 进召回与交集归因，打标→交集可还原

- 已发布内容的 `tagRefs` 必须进入召回与交集归因，并能还原到原始标签事实。

<a id="req-006"></a>
### REQ-006 搜索补充由 flag 控制，查询源唯一为 tag-service serving projection

- 搜索补充关闭时不得发起标签搜索；开启时只能查询 tag-service serving projection。

<a id="req-007"></a>
### REQ-007 常用标签、搜索结果和自动建议必须返回可由 tag-service 解析的 tagRef

- 常用标签、搜索结果和自动建议必须返回可由 tag-service 解析的 tagRef。
- 打标随内容生命周期：draft 可改 tagRefs，published 不可变（与既有内容一致）。
- 自动建议为辅助态，未经用户确认不得静默写入 published 内容的 tagRefs（避免不可控归因）。
- 取舍：统一查询 serving projection，避免端侧首发子集与全量 taxonomy 形成双真相源。

## 4. 契约引用

- canonical：`quwoquan_service/services/tag-service/contracts/tag/tag_node_view/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 各类型编辑页内联打标区，打标可选不拦截发布

- GIVEN 用户在图文/视频编辑页创作。
- WHEN 未选任何标签直接发布。
- THEN 发布成功，不因缺标签被拦截；打标区为可选内联区域。

<a id="gwt-002"></a>
### GWT-002 芯片集来自首发 launch 子集 + 自动建议，多选上限 5

- GIVEN 编辑页打标区渲染。
- WHEN 加载首发 launch 子集芯片与 suggestedTagRefs 自动建议芯片。
- THEN 芯片集合=launch 子集∪自动建议
- AND 多选最多 5
- AND 超限禁选。

<a id="gwt-003"></a>
### GWT-003 自动建议芯片可勾选/取消/删除，修正后 tagRefs 正确

- GIVEN 自动打标产出 suggestedTagRefs。
- WHEN 用户勾选/取消/删除自动建议芯片。
- THEN 未确认的自动建议不静默写入；最终 tagRefs 反映用户修正结果。

<a id="gwt-004"></a>
### GWT-004 选定 tagRefs 经 CreatePost 注入，发布后 content.tagRefs 一致

- GIVEN 用户选定若干 tagRef。
- WHEN 提交 CreatePost / UpdatePost(draft)。
- THEN content.tagRefs 含用户选定 + 已确认自动标签，与提交一致。

<a id="gwt-005"></a>
### GWT-005 tagRefs 进召回与交集归因，打标→交集可还原

- GIVEN 已发布内容含 tagRefs。
- WHEN 进入推荐召回与 IntersectionReason 生成。
- THEN tagRefs 参与召回；标签维度交集理由可还原。

<a id="gwt-006"></a>
### GWT-006 搜索补充由 flag 控制，查询源唯一为 tag-service serving projection

- GIVEN 搜索补充 feature flag 关闭。
- WHEN 渲染打标区。
- THEN 不渲染搜索入口；保留自动建议和已选标签。flag 开启后查询源唯一为 tag-service serving projection。

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 各类型编辑页内联打标区，打标可选不拦截发布

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：各类型编辑页打标可选路径 widget 测试通过。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 芯片集来自首发 launch 子集 + 自动建议，多选上限 5

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：芯片来源与上限 widget 测试通过。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 自动建议芯片可勾选/取消/删除，修正后 tagRefs 正确

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：自动建议修正路径 widget 测试通过。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 选定 tagRefs 经 CreatePost 注入，发布后 content.tagRefs 一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：payload 注入契约 + widget 测试通过。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 tagRefs 进召回与交集归因，打标→交集可还原

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：召回与交集归因集成测试覆盖。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 搜索补充由 flag 控制，查询源唯一为 tag-service serving projection

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：flag 开关两态 widget 测试通过。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效
