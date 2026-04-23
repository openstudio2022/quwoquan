# Runtime 总览

## 1. 定位

`runtime` 是 `quwoquan_service` 的横切公共能力层，用于承载多个业务服务共同依赖、但不应重复实现的运行时能力。

其核心目标是统一：

- 媒体资产模型与 URL 规范
- 实时通知与增量同步协议
- 事件 envelope 与版本治理
- 观测、幂等、重试、熔断等基础运行策略

## 2. 设计原则

### 2.1 业务归属与基础设施解耦

- 用户头像归 `user-service`
- 群头像归 `chat-service`
- 内容图片/视频归 `content-service`
- 上传、对象存储、CDN、URL 生成、同步 envelope 归 `runtime`

### 2.2 runtime 只提供能力，不吞业务语义

runtime 负责“怎么做得一致”，业务服务负责“何时触发、何时更新、谁有权限”。

### 2.3 URL 与 object identity 统一

业务数据库不直接依赖某一云厂商的临时 URL，而统一依赖：

- `assetId`
- `provider`
- `bucket`
- `objectKey`
- `version`

### 2.4 推拉混合同步

参考微信、企业微信等 IM 的公开经验，在线状态优先使用长连接通知，客户端通过 seq/cursor 主动拉取增量 patch；离线与弱网场景通过 gap fill 补偿。

## 3. runtime 的能力地图

### 3.1 media

- 上传会话
- 对象存储接入
- CDN 域名与签名 URL
- 图片/视频派生
- 头像策略

### 3.2 sync

- 用户同步流
- patch envelope
- cursor 与 seq
- 幂等、排序、补偿

### 3.3 realtime

- WebSocket topic 路由
- 在线通知
- 系统 Push 降级

### 3.4 governance

- 限流
- 熔断
- 重试
- 日志/指标/审计

## 4. 非目标

- 不在 runtime 中做消息发送鉴权。
- 不在 runtime 中定义群前 9 成员的业务排序规则。
- 不在 runtime 中定义帖子内容审核与推荐策略。
- 不在 runtime 中维护第二套 metadata 契约。

## 5. 交付要求

后续任何新能力若涉及以下任一项，必须先评估是否沉淀到 runtime：

- 多服务复用
- 客户端协议统一
- 供应商切换风险
- 跨服务对象引用
- 统一观测与治理

## 6. 推荐落地顺序

1. 冻结资产引用与 URL 规范
2. 冻结用户同步流模型
3. 接入头像与聊天媒体
4. 再扩展到内容图片、内容视频和更多实时场景
