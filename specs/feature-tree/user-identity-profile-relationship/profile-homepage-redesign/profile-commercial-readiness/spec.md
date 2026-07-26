# L3 Story：个人主页商用就绪（我的 + 他人主页） (`profile-commercial-readiness`)

> 所属能力：[`profile-homepage-redesign`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理账号、Persona 或关系的用户，我希望个人主页商用就绪 Story——我的主页数据加载、统计行、名字可设置等上线 gap 的最小价值闭环（V5 全量口径下保留并对齐），从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- 我的主页进入时加载当前用户档案（displayName/avatar/background 非 me 占位）
- 统计行（圈子/关注/粉丝）与列表数据同源
- 用户名字可设置并即时刷新

### Out of Scope

- 一级 Tab 收窄（历史去掉生活 Tab 的口径已被 V5 全量口径覆盖反转）
- 创作可见性过滤去除（历史去除口径已被 V5 恢复）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 我的主页数据加载与统计行同源

- 我的主页首屏展示真实档案与一致统计。production composition 只能通过
  `ProfileQuery` 的 generated Remote Facet 读取；alpha/test 的 adapter 只能由
  `runners/alpha` 或测试 override 注入，App 业务代码不得读取或切换数据源模式。

<a id="req-002"></a>
### REQ-002 技术：UI 通过 Provider 访问 Repository，禁止硬编码数据

- 技术：UI 通过 Provider 访问 Repository，禁止硬编码数据；统计与列表必须使用同一 Repository 方法保证一致性。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 我的主页数据加载与统计行同源

- GIVEN 已登录用户进入 /profile（ProfileMode.mine）。
- WHEN MyProfilePage 首帧触发 userDataProvider.loadUser(currentUserId)。
- THEN displayName/avatar/background 来自 ProfileQuery 的公开资料投影，非 me 占位；
  读取失败时不合成用户快照，ProfileShell 呈现同源可恢复失败态。
- THEN 统计行顺序圈子/关注/粉丝，数值来自 UserHomepageBundle 的 profileWithStats，
  与主页身份投影同一服务端聚合快照。

## 6. 依赖

- 前置要求：[`profile-homepage-redesign`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
