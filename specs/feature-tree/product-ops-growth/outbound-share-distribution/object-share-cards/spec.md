# L3 Story：对象分享卡片设计（object-share-cards） (`object-share-cards`)

> 所属能力：[`outbound-share-distribution`](../spec.md)

> Journey / Scenario：[`JNY-010 / SCN-023`](../../../spec.md#scn-023)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为产品运营或增长角色，
我希望海报渲染快照覆盖 5 类对象差异化主视觉与二维码/口令区，
从而获得可度量、可回滚的运营结果。

## 2. 范围与非目标

### In Scope

- “对象分享卡片设计（object-share-cards）”的输入、可观察主路径、失败语义以及与父能力的交接。
- 链接结构与入站回流。
- 分享面板交互编排（share-channel-panel）。
- 归因落库（share-attribution-and-token）。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 对象分享卡片设计（object-share-cards）

- 海报渲染快照覆盖 5 类对象差异化主视觉与二维码/口令区。

<a id="req-002"></a>
### REQ-002 海报含二维码与口令且视觉层级正确

- 海报渲染快照覆盖 5 类对象差异化主视觉与二维码/口令区。

<a id="req-003"></a>
### REQ-003 可见性分级控制卡片生成

- `public` 对象可生成站外卡片，`private` 对象不得生成外发卡片，未知可见性必须拒绝。

<a id="req-004"></a>
### REQ-004 缩略图与海报图来自 CDN 资产，禁止硬编码 URL（rule R28）

- 缩略图与海报图来自 CDN 资产，禁止硬编码 URL（rule R28）。

## 4. 契约引用

- canonical：`specs/feature-tree/product-ops-growth/outbound-share-distribution/object-share-cards/spec.md`
- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 对象分享卡片设计（object-share-cards）

- GIVEN 产品运营或增长角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“对象分享卡片设计（object-share-cards）”对应的公开行为。
- THEN 海报渲染快照覆盖 5 类对象差异化主视觉与二维码/口令区。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 海报含二维码与口令且视觉层级正确

- GIVEN 任一可分享对象生成海报。
- WHEN 海报渲染二维码、口令与对象主视觉。
- THEN 五类对象均保留正确的视觉层级和可识别的二维码、口令区域。

<a id="gwt-003"></a>
### GWT-003 可见性分级控制卡片生成

- GIVEN 对象可见性为 public、private 或未知值。
- WHEN 用户请求生成站外分享卡片。
- THEN public 可生成，private 被拒绝外发，未知值按安全语义拒绝。

## 6. 依赖

- 前置要求：[`outbound-share-distribution`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 微信会话/朋友圈卡按对象类型正确生成

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：5 类对象（含内容 4 形态）卡片字段映射测试通过。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 海报含二维码与口令且视觉层级正确

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：海报渲染快照覆盖 5 类对象差异化主视觉与二维码/口令区。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 可见性分级控制卡片生成

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：public/private/未知值卡片生成行为测试通过。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。
