# 实时通知与 Gap Fill

## 1. 目标

统一在线实时性与离线补偿机制。

## 2. 在线流程

1. 服务端生成 patch
2. realtime 网关通知在线设备“有更新”
3. 客户端调用 sync API 按 `afterSeq` 拉增量

## 3. 离线流程

1. 设备离线未收到实时通知
2. 下次启动或回前台时，客户端带 `afterSeq` 拉取
3. 服务端返回缺失 patch 列表

## 4. 为什么不用只推不拉

只推无法可靠处理：

- 网络抖动
- 客户端前后台切换
- 消息丢包
- 多端不同步

因此必须推拉结合。

## 5. gap fill 要求

- 返回顺序必须按 `syncSeq ASC`
- 单次返回量需要分页
- 支持 `hasMore`

## 6. 适配现有接口

聊天消息已存在 `/sync` 思路，后续应扩展到统一 `UserSyncStream` 能力，而不是只局限于 conversation message gap fill。
