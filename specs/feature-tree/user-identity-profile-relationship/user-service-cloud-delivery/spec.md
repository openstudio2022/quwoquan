# L2 Business Capability：用户服务云端交付 (`user-service-cloud-delivery`)

> 所属领域：[`user-identity-profile-relationship`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让用户资料、统计、设置和关系状态由 user-service 持久化，并通过正式远端契约在 App 各页面一致展示和更新。

## 2. 范围与非目标

### In Scope

- 用户资料、统计、设置和关系查询/命令的云端实现。
- App `UserProfileRepository` Remote 与 metadata/codegen 契约对齐。
- user-service 存储、缓存、错误、部署和三层测试证据。

### Out of Scope

- 个人主页的视觉布局；由 [`profile-homepage-redesign`](../profile-homepage-redesign/spec.md) 负责。
- 登录 token 生命周期；由 [`auth-profile-snapshot`](../auth-profile-snapshot/spec.md) 负责。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-002`](../../spec.md#scn-002)
  - 本能力接收：合法身份和用户资料命令/查询。
  - 本能力处理：资料、统计、设置和关系事实的持久化与读取。
  - 本能力输出：跨页面一致的用户 projection 或 canonical failure。
  - 失败时终态：保持既有事实并提供明确恢复动作。

## 4. Story



- [`remote-profile-delivery`](./remote-profile-delivery/spec.md)：App 必须经 generated operation/Facet 读写资料；请求失败不得返回 Mock 或本地合成成功，切换主体后必须清除旧主体投影。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 用户事实由云端 owner 持久化

- user-service 必须拥有用户资料、设置及关系操作的写入事实，并向 App 提供稳定 projection。
- domain、application、adapter 和 infrastructure 保持单向依赖；domain 不得依赖数据库驱动。
- 新对象、字段、operation、event 或 error 必须先更新 metadata 并经 codegen 进入端云。

<a id="req-002"></a>
### REQ-002 App Remote 与失败语义单轨

- App Remote 必须使用生成 operation 与 `CloudRuntimeConfig`，不得默认切回 Mock。
- 服务错误、端侧 `CloudException/RuntimeFailure`、用户恢复动作和测试必须引用 canonical error。
- cache miss 或缓存故障不得伪造空资料；按恢复策略读取 owner store 或返回明确失败。

## 6. 契约与依赖

- 上游能力：身份进入和授权上下文。
- 下游能力：个人主页、关系列表、设置及使用用户资料的其他领域。
- 读取事实：用户、关系和设置 owner projection。
- 写入事实：仅通过 user-service 公开 command。
- operation/event/object/error：引用 `quwoquan_service/services/user-service/contracts/`。
- 一致性要求：资料更新、缓存失效和 projection 版本必须可观测；不得双写 Mock 状态。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 资料更新跨页面一致

- GIVEN 用户已认证且 user-service、metadata 生成契约和 App Remote 配置有效。
- WHEN 用户更新资料或关系状态并在个人主页及相关列表重新读取。
- THEN owner store 返回的新版本通过同一 Remote 契约投影到各页面。
- AND 存储、缓存或契约失败返回 canonical failure，不显示伪造成功或 Mock 数据。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 匹配环境的端云验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：需要持续证明 user-service 真实存储、App Remote 和跨页面 projection 在目标环境一致。
- 完成判定：`SIT-001` 具有匹配环境的 `api_integration` 和 `user_acceptance` `spec_ref`。

<a id="open-002"></a>
### OPEN-002 身份与资料 operation 对象化收口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：手写路由、客户端身份头或聚合接口绕过对象契约时，owner 与授权语义会分叉。
- 完成判定：`SIT-001` 的同一 Remote 契约跨页面投影子句成立——App 暴露的身份/资料 operation 全部使用生成契约和可信 principal，且无手写旧路由或客户端身份头旁路。
