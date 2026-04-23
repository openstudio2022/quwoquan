# 用户同步流

## 1. 定义

用户同步流是所有客户端可见变化的统一增量通道，按用户维度组织，而不是按会话、按群头像、按用户资料分别组织。

## 2. 为什么按用户维度

这样可以让客户端只维护一个主 cursor，避免：

- 每个会话一个 seq
- 每个对象类型一套协议
- 多端状态难以补偿

## 3. patch 类型

建议首批支持：

- `message.created`
- `message.recalled`
- `conversation.updated`
- `conversation.roster.updated`
- `conversation.avatar.updated`
- `user.profile.updated`
- `user.avatar.updated`
- `receipt.updated`
- `badge.updated`

## 4. 生产者

- `chat-service`
- `user-service`
- `content-service`（后续如需客户端订阅）

## 5. 消费者

- app
- 未来的桌面端/网页端

## 6. 边界

用户同步流承载的是“变化通知与增量数据”，不承载媒体二进制正文。
