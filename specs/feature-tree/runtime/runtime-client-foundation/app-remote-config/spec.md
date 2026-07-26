# L3 Story：App 远程运营配置（app-remote-config） (`app-remote-config`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望统一 App 远程运营配置的 schema、缓存、激活、投影、灰度与验收，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- AppRemoteConfig 字段目录与 schema 风险分级
- /config/app 元信息增强与规范投影
- 端侧 LKG 缓存、后台刷新与消费者收口
- 配置发布、漂移、灰度、回滚观测契约

### Out of Scope

- gateway/CDN/auth/secret/payment/security policy 热更新
- 控制面完整 UI 实现
- 第三方 Remote Config SaaS 接入

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 启动不阻塞且有默认可用配置

- 冷启动首帧可在无远程配置的情况下正常进入欢迎页和首页
- 首页频道、评论与 feature flag 由本地默认值提供
- 远程配置失败不会阻塞首帧或产生白屏

<a id="req-002"></a>
### REQ-002 LKG 优先和后台刷新

- 启动后优先使用磁盘 LKG 作为 active 配置
- 远程 fresh 配置仅在后台刷新并进入 pending
- 当前会话内不会出现频道结构跳变

<a id="req-003"></a>
### REQ-003 配置接口统一消费

- comment/home/intersection 等消费者统一走 AppRemoteConfig facade
- 页面构建过程中不再重复拉取 /config/app
- 新配置字段通过统一 provider 下发到消费者

<a id="req-004"></a>
### REQ-004 服务端快照可缓存可回滚

- /config/app 响应包含可审计的快照元信息
- ETag 命中时可返回轻响应
- 回滚后新会话拿到回滚后的 packageVersion / configHash

<a id="req-005"></a>
### REQ-005 App 首帧不得等待远程配置网络请求

- App 首帧不得等待远程配置网络请求。
- 无网络、配置接口失败、schema 不兼容时，App 必须使用 LKG 或 codegen defaults。
- kill switch 可 immediate 生效，但必须有最小 payload、短 TTL、审计与回滚。
- local_contract：配置目录、schema、禁止字段、feature flag expiry 与页面可运营矩阵静态校验。

## 4. 契约引用

- canonical：`/config/app`
- canonical：`AppRemoteConfigSnapshot`
- canonical：`AppRemoteConfigStore`
- canonical：`AppRemoteConfigSnapshot.activationPolicy`
- canonical：`contentRuntimeConfigProvider`
- canonical：`AppRemoteConfig`
- canonical：`ConfigProjectionService`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 启动不阻塞且有默认可用配置

- GIVEN 首次安装且本地没有远程配置缓存
- GIVEN /config/app 网络不可达
- WHEN App 冷启动进入欢迎页和首页
- THEN 首帧不等待远程配置
- THEN 首页频道、评论、feature flag 使用 codegen defaults
- THEN 不出现白屏或阻塞性配置错误

<a id="gwt-002"></a>
### GWT-002 LKG 优先和后台刷新

- GIVEN 本地存在上一份稳定配置
- WHEN App 启动后远程返回新 configHash
- THEN 启动立即激活 LKG
- THEN 普通字段写入 pending next-session
- THEN 当前会话不发生首页频道结构跳变

<a id="gwt-003"></a>
### GWT-003 配置接口统一消费

- GIVEN 评论输入、评论列表、首页频道和交集卡都需要配置
- WHEN 页面首次构建
- THEN 组件不得直接重复拉取 /config/app
- THEN 配置均从 AppRemoteConfig/contentRuntime facade 读取

<a id="gwt-004"></a>
### GWT-004 服务端快照可缓存可回滚

- GIVEN 控制面发布新配置包
- WHEN 客户端请求 /config/app
- THEN 响应包含 schema/packageVersion/configHash/maxAgeSec
- THEN ETag 可用于未变更轻响应
- THEN 回滚后新会话获得回滚版本 hash

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
