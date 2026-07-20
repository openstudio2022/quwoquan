# L3 特性：App 远程运营配置（app-remote-config）

## 背景与目标

当前 App 启动基础配置走 `app_runtime.yaml -> --dart-define -> CloudRuntimeConfig`，远程运营配置走内容域 `/config/app -> contentRuntimeConfigProvider`。两条链路职责不同，但现状容易混称为“启动配置”，并且远程配置仍存在懒加载、重复拉取、无磁盘 LKG、无统一发布闭环等问题。

本 L3 的目标是建立 `AppRemoteConfig` 主线：以本地默认与最近稳定快照保障启动可用，以 `/config/app` 下发可运营参数，以控制面配置包保障审计、灰度、回滚与生效率可见。

## In Scope

1. 明确四类配置边界：
   - `BuildRuntimeConfig`：构建期/环境期常量，继续由 `app_runtime.yaml` 与 `--dart-define` 管理。
   - `AppRemoteConfig`：App 可公开消费的运营参数、轻系统参数、feature flag、kill switch。
   - `ServiceRuntimeConfig`：服务实例内部配置，只经服务端 runtime-config 消费。
   - `PageDataBundle`：页面业务数据，不混入全局配置。
2. 建立 `AppRemoteConfigSnapshot` 契约：`schema`、`packageVersion`、`configHash`、`fetchedAt`、`maxAgeSec`、`activationPolicy` 与业务 payload（单轨当前形状，禁止 `schemaVersion` 信封或协议版本分支）。
3. 端侧支持 default / disk LKG / network fresh 三层来源，启动不阻塞首帧。
4. 收口现有 `comment`、`home_channels`、`intersection`、`client_state_sync`、`feature_flags`、`gray_release` 到统一 provider。
5. 为配置字段建立 owner、risk、reload、activation、expiry、fallback 与验收口径。

## Out of Scope

- 不允许通过 AppRemoteConfig 热更新 gateway、CDN、鉴权、密钥、支付、安全权限、数据权限裁决。
- 不支持远程新增 App 不认识的新页面模板或路由表。
- 不在本 L3 一次性完成运营控制台 UI；本 L3 先冻结 schema、投影、缓存和验收契约。
- 不引入第三方 Remote Config SaaS 作为主真相源。

## 核心契约

`/config/app` 目标响应必须至少包含：

```json
{
  "schema": "app_remote_config",
  "packageVersion": "cfg_2026_06_06_001",
  "configHash": "sha256:...",
  "fetchedAt": "2026-06-06T01:00:00Z",
  "maxAgeSec": 21600,
  "activationPolicy": {
    "default": "next_session",
    "kill_switches": "immediate"
  },
  "content": {}
}
```

## 产品与运营范围

首批纳入：
- 首页频道：显示/隐藏、排序、模板、feed_query、mood copy。
- 评论体验：字数、回复预览数、展开页大小、附件上限、默认排序、折叠行数。
- 交集展示：默认展开行数、候选窗上限。
- 客户端同步：flush 延迟、retry 延迟、批量上限、前后台触发策略。
- Feature flags：文章书本阅读、卷角、身份 IA、分享模板、persona 管理等。

首批不纳入：
- gateway/CDN/鉴权/密钥/支付/安全策略。
- 路由表新增/删除。
- 需要新代码支持的新页面模板。
- 数据权限、审核、安全合规裁决。

## 非功能要求

- App 首帧不得等待远程配置网络请求。
- 无网络、配置接口失败、schema 不兼容时，App 必须使用 LKG 或 codegen defaults。
- 会话级字段默认 next-session 生效，避免频道、骨架、实验 bucket 中途跳变。
- kill switch 可 immediate 生效，但必须有最小 payload、短 TTL、审计与回滚。
- `/config/app` 应支持 `ETag` / `If-None-Match`、多级缓存与预计算快照。

## 验收摘要

- local_contract：配置目录、schema、禁止字段、feature flag expiry 与页面可运营矩阵静态校验。
- local_contract：端侧 default/LKG/network/pending/immediate 状态机与消费者收口测试。
- api_integration：服务端投影、ETag、快照缓存、回滚 hash 与高并发冷启动集成测试。
- user_acceptance：运营灰度发布、生效率看板、SLO 失败回滚与审计记录演练。
