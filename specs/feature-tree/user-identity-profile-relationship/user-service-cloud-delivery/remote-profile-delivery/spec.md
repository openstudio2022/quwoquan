# L3 Story：用户资料远端交付 (`remote-profile-delivery`)

> 所属能力：[用户服务云侧交付](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理账号与 Persona 的用户，我希望资料、统计和关系状态由 user-service 持久化并跨页面一致展示，从而在刷新、重启或切换设备后仍看到真实状态。

## 2. 范围与非目标

### In Scope

- 资料读取与更新、资料快照、统计和关系投影的 Remote 消费。
- metadata-first、typed Facet、canonical error/recovery 与登录主体隔离。

### Out of Scope

- 主页视觉布局、内容互动事实和端侧合成统计。

## 3. 行为要求

### REQ-001 Owner 资料与投影单轨

- App 必须经 generated operation/Facet 读写资料；请求失败不得返回 Mock 或本地合成成功，切换主体后必须清除旧主体投影。

## 4. 契约引用

- profile：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- profile view：`quwoquan_service/services/user-service/contracts/account/user_account/projections/user_profile_view.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 更新后跨页面读取同一资料

- GIVEN 用户以 Persona A 登录并持有服务端资料快照。
- WHEN 用户更新资料后刷新我的主页和作者主页，再切换到 Persona B。
- THEN Persona A 的页面读取同一 owner 版本，Persona B 不残留 A 的资料；远端失败时展示 canonical recovery 而非本地成功。

## 6. 依赖

- 前置要求：认证主体、Persona 上下文和 user-service 可用。
- 上游事实：用户输入、快照版本与登录主体。
- 下游结果：持久化资料投影或结构化失败。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 跨设备资料一致性证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：本节点尚缺 App Remote、真实存储和主体切换的组合证据。
- 完成判定：`GWT-001` 具有 local_contract、api_integration 和 user_acceptance 的直接 `spec_ref`。
