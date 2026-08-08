# L3 Story：认领是共享主页可信治理的关键入口 (`homepage-claim-request-and-review`)

> 所属能力：[`homepage-claim-maintain-and-offline`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览、补充或维护共享主页的用户，
我希望审核通过前不得显示官方认领标识，
从而获得可信且可持续维护的对象主页。

## 2. 范围与非目标

### In Scope

- “认领是共享主页可信治理的关键入口”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 认领是共享主页可信治理的关键入口

- “认领是共享主页可信治理的关键入口”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 审核通过前不得显示官方认领标识

- 审核通过前不得显示官方认领标识。

<a id="req-003"></a>
### REQ-003 认领页通过 production Remote 完成登录续接、申请提交与待审回读

- 认领页必须先读取当前主页的可写状态；未登录时保留同一主页和未提交表单意图，登录成功后只恢复这一条认领旅程。
- 申请只经 `entity.homepage_claim_request` 的公开写入口创建，并以 typed receipt 与后续 canonical readback 共同确认进入待审；页面不得自行显示已认领或代替治理方审核。
- 已下线、已认领、输入无效、身份拒绝或 Remote 不可用时必须保留可恢复终态，不得重复创建申请或以 Toast 冒充成功。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage_claim_request/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 认领是共享主页可信治理的关键入口

- GIVEN 浏览、补充或维护共享主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“认领是共享主页可信治理的关键入口”对应的公开行为。
- THEN 通过父能力公开契约交付“认领是共享主页可信治理的关键入口”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 认领页 production Remote 旅程与失败恢复

- GIVEN 用户从已发布且尚未认领的共享主页进入认领页，App 使用 production Remote composition，且当前身份可能尚未登录。
- WHEN 用户完成登录续接并提交认领材料。
- THEN 页面读取的主页状态、创建申请的 typed receipt 与后续待审 readback 属于同一主页和同一申请意图；审核通过前仍不显示官方认领标识。
- THEN 已下线、已认领、输入无效、身份拒绝或 Remote 失败均进入可区分终态；未提交表单在安全范围内保留，重试不产生第二份申请或伪成功提示。
- THEN 页面只负责认领申请的读取与创建，审核、批准和拒绝仍由治理 owner 的公开行为决定，不由 App 本地状态代替。

## 6. 依赖

- 前置要求：[`homepage-claim-maintain-and-offline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 认领页 production Remote 双真机验收

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：规格已明确登录续接、typed receipt、待审回读与失败恢复，但尚无同一 candidate 的 production Remote Journey CaseResult 证明这些行为在真实设备成立。
- 完成判定：`GWT-002` 的每条结果在物理 Android 与物理 iPhone 上通过，且两类 ReadinessResultBundle 绑定同一 commit、ContractGraph、candidate、environment 与非内存 Provider。
- 依赖：对象级 `user_acceptance` runner、真实测试身份、治理方可读的待审结果与可信 ResultBundle；编译、Widget、模拟器或动态 skip 均不计通过。
