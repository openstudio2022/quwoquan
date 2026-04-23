# Realtime 总览

## 1. 目标

为在线设备提供低延迟变化通知，但不承担完整状态同步职责。

## 2. 定位

realtime 是：

- 在线 hint 通道
- topic 路由层
- WebSocket / Push 的统一封装

realtime 不是：

- 全量状态同步通道
- 媒体文件传输通道

## 3. 原则

- 优先通知，不承诺单独完成最终一致
- 最终一致由 `sync` 兜底
