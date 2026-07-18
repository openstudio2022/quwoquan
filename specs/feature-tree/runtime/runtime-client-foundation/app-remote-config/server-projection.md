# /config/app 服务端投影链路

## 目标态

`content-service` 当前使用规范投影，但长期目标不是在 `PostService.GetAppConfig()` 手写业务配置。目标链路为：

```text
contracts/metadata/**/ui_config.yaml
  + specs/gates/app_remote_config_catalog.yaml
  + control-plane config_package/config_release
  -> runtime/controlplane.ResolveEffectiveConfig
  -> AppConfigProjectionService
  -> signed/precomputed app snapshot
  -> content-service /config/app
```

## 投影职责

| 层 | 职责 | 禁止 |
|---|---|---|
| metadata/catalog | 字段、owner、risk、fallback、expiry、client_visible | 手写第二套字段说明 |
| control plane | 编辑、审批、灰度、回滚、release pointer | 直接改服务代码发布运营配置 |
| projection service | 合并 layer、生成 hash/ETag | 下发 secret/auth/payment/security config |
| content-service adapter | 读取预计算快照、处理 ETag/304、兜底 embedded snapshot | 重新维护业务配置真相源 |

## 当前投影

当前实现下发 `schema/packageVersion/configHash/fetchedAt/maxAgeSec/activationPolicy/content`，其中 `content.comment`、`content.feature_flags`、`content.gray_release`、`content.client_state_sync` 均采用 canonical snake_case 结构；禁止 `schemaVersion` 或数字协议版本。

## 迁移切片

1. M1：`PostService.GetAppConfig()` 输出标准 envelope 和 hash，handler 支持 ETag。
2. M2：新增 `AppConfigProjectionService`，输入为 `ResolveEffectiveConfig` 输出和 catalog。
3. M3：content-service 启动时加载预计算快照，运行时仅按指针读取。
4. M4：platform-ops-service 暴露发布/回滚 API 与生效率事件。
5. M5：删除 content-service 内手工业务拼装，仅保留 embedded fallback。

## 回滚

- 配置回滚只切 release pointer，不重新部署 App。
- 服务端若控制面不可用，继续服务最近快照。
- 快照无法解析时使用 embedded fallback，并输出 `source=embedded_fallback` 指标。
