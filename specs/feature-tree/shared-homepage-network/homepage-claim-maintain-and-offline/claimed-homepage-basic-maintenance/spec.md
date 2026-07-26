# L3 Story：认领方维护主页基础资料 (`claimed-homepage-basic-maintenance`)

> 所属能力：[`homepage-claim-maintain-and-offline`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望认领 owner 维护主页基础资料（UpdateClaimedHomepageBasics），从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- homepageMaintenance 页编辑副标题/地址/封面等基础字段并提交。
- 仅 claimed owner persona 可写（claimed_homepage_owner ownership policy）。
- CAS 版本冲突的结构化恢复（version_conflict → refresh）。

### Out of Scope

- 认领审批流本身（homepage-claim-request-and-review）。
- canonical identity/entity_homepage/homepageType 修改（创建后不可变）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 认领 owner 更新基础资料且非 owner 被拒

- `UpdateClaimedHomepageBasics` 仅允许认领方修改基础资料，并以结构化错误拒绝越权写入和版本冲突。

<a id="req-002"></a>
### REQ-002 认领方不能直接删改真实用户口碑和记录用户内容

- 认领方不能直接删改真实用户口碑和记录用户内容。
- 维护操作必须有清晰可审计边界。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 认领 owner 更新基础资料且非 owner 被拒

- GIVEN 主页 claimStatus=claimed 且当前 persona 为 owner。
- WHEN owner 提交基础资料变更；非 owner persona 尝试提交。
- THEN owner 提交成功并回详情页刷新；非 owner 得到结构化 permission_denied(403)。
- THEN 版本冲突返回 version_conflict(409) 且页面给出刷新恢复动作。

## 6. 依赖

- 前置要求：[`homepage-claim-maintain-and-offline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 认领 owner 更新基础资料且非 owner 被拒

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：认领 owner 可更新基础资料，非 owner 与版本冲突返回结构化失败。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
