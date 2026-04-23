# runtime-media 容量验证基线

## 目标
冻结当前版本已经验证过的容量场景、边界和非目标，确保放量时能明确回答“验证过什么、没验证什么”。

## 容量假设
- 热点群：同一群在短时间内连续发生加人、退群、头像更新
- 大 fanout：单次 `conversation.avatar.updated` 需要广播到大量成员
- 长离线追赶：客户端从较老 `syncSeq` 开始分批追 patch
- 高频 hint：客户端短时间内收到多次 `sync_hint`
- 大本地列表：本地会话列表超过 200 条，且存在孤儿会话清理

## 已验证场景
1. Redis score queue 支持热点群任务去重与重试，不阻塞建群/加人/退群主流程。
2. `runtime/sync` 支持批量写 patch 与分批拉取，gap 明确返回 `requiresResync`。
3. 客户端对高频 hint 做防抖合并，只触发一次头像 patch 拉取。
4. 本地会话缓存支持 namespace 隔离，并可清理超出首批分页窗口的孤儿会话。

## 当前安全放量边界
- 服务端：
  - 群头像重算依赖 Redis 轻量任务模型，可支撑当前阶段预发与中等规模灰度
  - patch 拉取按批次工作，适合长离线追赶，但仍不是企业级独立 MQ
- 客户端：
  - 高频 hint 已合并，避免因瞬时 burst 造成重复 pull
  - `requiresResync` 作为显式缺洞语义，避免静默错乱

## 已知风险点
- Redis 任务队列仍与完整企业级 MQ 存在能力差距
- 默认群图标降级比例与 hint-to-pull 仍需依赖客户端埋点或预发抓样
- 当前未引入真机自动化大规模弱网回放

## 非目标
- 跨机房灾难恢复压测
- 百万级 recipient 的企业级广播验证
- 真机农场全自动弱网长跑

## 复现入口
- `go test ./quwoquan_service/runtime/sync`
- `go test ./quwoquan_service/services/chat-service/internal/application`
- `go test ./quwoquan_service/services/chat-service/tests`
- `flutter test test/cloud/realtime/realtime_avatar_sync_handler_test.dart`
- `flutter test test/core/services/local_chat_search_sync_service_test.dart`
