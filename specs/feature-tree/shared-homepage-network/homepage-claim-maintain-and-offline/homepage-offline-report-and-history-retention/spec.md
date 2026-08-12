# L3 Story：用户上报主页状态异常 (`homepage-offline-report-and-history-retention`)

> 所属能力：[`homepage-claim-maintain-and-offline`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望用户上报主页状态异常，审核 confirmed_offline 后主页下线但历史保留，从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- homepageStatusReport 页提交纠错/歇业上报（CreateHomepageStatusReport）。
- Ops portal 查询待审队列并执行 confirmed_offline/dismissed 审核。
- confirmed_offline 经事件驱动 Homepage 下线并从搜索删除。
- 下线后详情返回 homepage_offline(410) 语义，历史口碑/挂载记录保留不硬删。

### Out of Scope

- 上报处理结果的站内信通知。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 状态上报进入待审并在确认后下线保留记录

- `List/Create/ReviewHomepageStatusReport` 必须通过真实 Ops Portal 消费面执行，并遵循统一权限与审计边界。
- 下线与举报命令必须返回 receipt，以 CAS 保护终态并经 outbox 更新读模型；页面只在 receipt 成功后展示提交成功。

<a id="req-002"></a>
### REQ-002 baseline 统一采用软下线

- 主页状态异常统一采用软下线并保留历史事实。
- 已下线主页不得直接物理删除。
- 搜索与推荐可降级，但不可阻断记录访问。

<a id="req-003"></a>
### REQ-003 状态上报页通过 production Remote 提交待审事实并保留恢复上下文

- 页面必须先读取当前主页可上报状态，未登录时只续接同一主页与同一未提交表单。
- 上报只经 `entity.homepage_status_report` 的公开写入口创建；typed receipt 与待审 readback 成立后才可表达提交成功。
- 页面不拥有审核或下线决定；重复提交、主页已下线、身份拒绝或 Remote 失败均不得清空有效输入、创建重复事实或伪造已下线结果。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage_status_report/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage_status_report/events.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 状态上报进入待审并在确认后下线保留记录

- GIVEN persona 在已发布主页发现状态异常，App 使用 production Remote composition；未登录时可在登录后续接同一主页和未提交表单。
- WHEN persona 提交原因与描述，随后治理 operator 审核 confirmed_offline 或 dismissed。
- THEN 上报以可信 persona 落库 pending_review；同 reporter 同 reason 去重。
- THEN 页面只在 typed receipt 与 canonical pending readback 一致后表达提交成功；输入无效、身份拒绝、Remote 失败或主页已下线时保留可恢复终态，且不新增重复上报。
- THEN confirmed_offline 后主页 status=offline、搜索投影删除、详情呈现下线语义。
- THEN 历史评价与挂载记录保留（禁止回退为硬删除）。
- THEN 同 actor/idempotency-key/digest 重放返回同一结果，审核终态不可互改。
- THEN 审核事实经 durable outbox 与 checkpoint 幂等投影到 Homepage。

<a id="gwt-002"></a>
### GWT-002 状态上报页 production Remote 旅程与失败恢复

- GIVEN 用户从已发布共享主页进入状态上报页，App 使用 production Remote composition，且当前身份可能尚未登录。
- WHEN 用户完成登录续接，选择原因并提交状态上报。
- THEN 页面读取的主页状态、创建上报的 typed receipt 与 `GetMyPendingHomepageStatusReport` authoritative readback 属于同一主页、同一 persona、同一原因和同一上报意图；只有 receipt 与 readback 一致且均为 `pending_review` 时才表达提交成功。
- THEN 输入无效、身份拒绝、主页不存在、Remote 失败或 readback 未收敛时保留安全范围内的未提交表单与显式恢复动作；同一表单意图重试复用同一幂等键且不产生第二条上报或伪成功提示。
- THEN 页面只负责状态上报的读取与创建，`confirmed_offline` 或 `dismissed` 的治理裁决、下线投影与历史保留仍由治理 owner 的公开行为决定。

## 6. 依赖

- 前置要求：[`homepage-claim-maintain-and-offline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 状态上报 production Remote 双真机验收

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前缺少从真实页面提交、待审回读到治理终态投影的同 candidate 端云 Journey 证据，不能由本地 receipt、Widget 或 Ops 单侧审核结果代替。
- 完成判定：`GWT-001` 的治理终态与 `GWT-002` 的页面提交、失败恢复、幂等重放均有可信 CaseResult，且物理 Android 与物理 iPhone 的 ReadinessResultBundle 绑定同一 commit、ContractGraph、candidate、environment 与非内存 Provider。
- 依赖：对象级 `user_acceptance` runner、真实 persona/operator、可回读待审与审核结果的 production Remote 环境；skipped 或仅本地证据均不计通过。
