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

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage_status_report/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage_status_report/events.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 状态上报进入待审并在确认后下线保留记录

- GIVEN 已登录 persona 在已发布主页发现状态异常。
- WHEN 提交 reason+描述；治理 operator 审核 confirmed_offline 或 dismissed。
- THEN 上报以可信 persona 落库 pending_review；同 reporter 同 reason 去重。
- THEN confirmed_offline 后主页 status=offline、搜索投影删除、详情呈现下线语义。
- THEN 历史评价与挂载记录保留（禁止回退为硬删除）。
- THEN 同 actor/idempotency-key/digest 重放返回同一结果，审核终态不可互改。
- THEN 审核事实经 durable outbox 与 checkpoint 幂等投影到 Homepage。

## 6. 依赖

- 前置要求：[`homepage-claim-maintain-and-offline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
