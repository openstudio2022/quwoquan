# L3 Story：运行时不可恢复异常受控重新进入 (`unrecoverable-runtime-recovery`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为正在使用应用的用户，
我希望根级故障发生后只执行一次安全、可理解的重新进入，失败时立即切换到更新或网页版，
从而保留账号和本地数据并避免无限恢复循环。

## 2. 范围与非目标

### In Scope

- 安全 Shell 后根 Router、根状态容器或根渲染树确认失效的不可恢复异常。
- R0 落地、R1 重新进入、R2 成功和 R3 失败四个状态。
- 主容器、导航栈和临时页面状态的一次性重建，以及登录态恢复和首页替换路由。
- 重新进入失败后的版本确认、Android 官网 APK、公众 iOS PWA 和官方网页版恢复。

### Out of Scope

- 页面、区块、网络、权限、媒体和非关键模块的局部错误恢复。
- 第二次重新进入、进程自动重启或清除草稿、账号凭据、缓存和业务数据库。
- “恢复成功”中间页面。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 运行时根级异常进入固定落地页

- R0 显示“应用暂时无法继续使用／重新进入后将返回首页／重新进入应用／使用网页版”。
- 详细异常静默保存和异步上报，页面不显示技术原因、日志状态或诊断信息。

<a id="req-002"></a>
### REQ-002 主容器最多重建一次

- 点击后进入 R1，显示“正在重新进入应用／完成后将自动返回首页／正在重新进入…／使用网页版”。
- 恢复宿主停止固定登记的根级任务，销毁当前业务 ProviderScope、Router 和临时页面状态，再创建新主容器并恢复登录态；不得删除长期用户数据。
- 成功后以替换路由进入首页，不展示中间页且不能返回异常页；首页可显示约 2 秒“已重新进入应用”。

<a id="req-003"></a>
### REQ-003 重新进入失败不得循环

- 重建超时或再次发生根级异常后立即进入 R3 并检查版本。
- 有新版时显示“当前版本需要更新／更新后即可继续使用”，已最新时显示“当前已是最新版本／请使用网页版继续”，检查未完成时显示“应用暂时无法继续使用／请使用网页版继续”。
- R3 不再出现“重新进入应用”。

<a id="req-004"></a>
### REQ-004 网页版在全部运行时恢复状态可用

- R0、R1 和 R3 的网页版动作始终可用。
- 可用登录态允许尝试短时、单次授权交换；失败仍打开网页版登录页，长期 Token 不得进入 URL。
- 网页打开失败只显示“网页暂时无法打开，请稍后再试”，不增加常驻第二恢复说明。

## 4. 契约引用

- 版本与下载：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/operations.yaml`
- 恢复异常：`quwoquan_service/services/product-ops-service/contracts/product_ops/recovery_failure/operations.yaml`
- 会话：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 一次性重新进入成功

- GIVEN 安全 Shell 后发生根级不可恢复异常且本进程尚未尝试重新进入。
- WHEN 用户点击“重新进入应用”。
- THEN 旧根级任务和临时导航状态被销毁，新容器恢复登录态并替换路由进入首页，异常页不可返回。

<a id="gwt-002"></a>
### GWT-002 重新进入失败后转入外部恢复

- GIVEN 一次性重建超时或再次发生根级故障。
- WHEN 系统进入 R3 并检查版本。
- THEN 用户只能选择经确认的更新通道或网页版，不再出现重新进入动作且不形成循环。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 协作 Story：[`cold-start-performance`](../cold-start-performance/spec.md)、[`public-content-web-entry`](../public-content-web-entry/spec.md)。
- 父级设计：[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真机主容器重建与登录态恢复证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Android/iPhone 真机的一次性根容器重建、首页首帧、登录态恢复和失败转版本链的真实环境录像与日志证据。
- 完成判定：`GWT-001`、`GWT-002` 在 Beta 和 Gamma 的 production Remote composition 中通过，并完成 Prod 发布前真机验证。
