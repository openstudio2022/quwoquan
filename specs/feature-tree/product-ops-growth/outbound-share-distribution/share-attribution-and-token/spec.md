# L3 Story：分享归因与口令（share-attribution-and-token） (`share-attribution-and-token`)

> 所属能力：[`outbound-share-distribution`](../spec.md)

> Journey / Scenario：[`JNY-010 / SCN-023`](../../../spec.md#scn-023)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为通过站外链接或口令进入应用的用户，
我希望让短链、二维码和口令解析到同一 canonical 对象并保留安全归因，
从而稳定到达目标内容且不被伪造参数劫持。

## 2. 范围与非目标

### In Scope

- “分享归因与口令（share-attribution-and-token）”的输入、可观察主路径、失败语义以及与父能力的交接。
- 卡片视觉（object-share-cards）。
- 面板交互（share-channel-panel）。
- 入站解析路由（runtime/external-inbound-deeplink-routing 提供 resolver）。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分享归因与口令（share-attribution-and-token）

- 口令、二维码与短链必须解析到同一目标对象和归因上下文。

<a id="req-002"></a>
### REQ-002 口令三路径同源回流并归因

- 口令、二维码与短链必须解析到同一目标对象和归因上下文。

<a id="req-003"></a>
### REQ-003 5 类对象分享落库端云一致

- 五类可分享对象必须写入同一分享事实结构，并保留对象类型与对象 ID。

<a id="req-004"></a>
### REQ-004 分享与安装归因可按渠道与对象统计

- 分享与安装归因必须按渠道、对象类型和目标环境聚合，且维度口径与事件目录一致。

<a id="req-005"></a>
### REQ-005 分享落库与短链/口令契约

- share_id/utm 落库字段、短链解析、口令结构来自 metadata，端云一致。

<a id="req-006"></a>
### REQ-006 归因不丢（rule R21/R23）：referralSource/share_id/utm 端云贯穿；sessionId/feedRequestId 语义统一

- 归因不丢（rule R21/R23）：`referralSource/share_id/utm` 端云贯穿；`sessionId/feedRequestId` 语义统一。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/outbound_share_fact/operations.yaml#CreateOutboundShare`
- canonical：`specs/feature-tree/runtime/runtime-client-foundation/external-inbound-deeplink-routing/spec.md`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`
- canonical：`specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/analytics-metric-dictionary/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 分享归因与口令（share-attribution-and-token）

- GIVEN 产品运营或增长角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“分享归因与口令（share-attribution-and-token）”对应的公开行为。
- THEN 三种入口均打开同一目标对象，并携带一致的 `referralSource/share_id/utm`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 口令三路径同源回流并归因

- GIVEN 用户通过口令、二维码或短链进入应用。
- WHEN 系统解析并恢复目标对象。
- THEN 三条路径得到同一对象与归因上下文，且伪造参数不改变目标。

<a id="gwt-003"></a>
### GWT-003 5 类对象分享落库端云一致

- GIVEN 用户分享任一支持的对象类型。
- WHEN 分享事实写入并由端侧读取。
- THEN 五类对象使用同一事实结构，并保留准确的对象类型与对象 ID。

<a id="gwt-004"></a>
### GWT-004 分享与安装归因可按渠道与对象统计

- GIVEN 分享或安装归因事件被记录。
- WHEN 运营按渠道、对象类型和目标环境查询。
- THEN 聚合结果与事件目录的维度口径一致且可追溯。

## 6. 依赖

- 前置要求：[`outbound-share-distribution`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 每次分享生成归因并注入对外物料

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：各渠道注入归因的契约测试通过。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 口令三路径同源回流并归因

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：口令/二维码/短链三路径解析一致性测试通过。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 5 类对象分享落库端云一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：5 类对象分享落库契约测试通过。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 分享与安装归因可按渠道与对象统计

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：埋点维度与指标口径契约测试通过。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 分享落库与短链/口令契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：share_id/utm 落库字段、短链解析、口令结构来自 metadata，端云一致。
- 完成判定：`GWT-002` 的三路径同源解析与 `GWT-003` 的分享事实落库对应行为满足——share_id/utm 落库字段、短链解析、口令结构来自 metadata，端云一致。
