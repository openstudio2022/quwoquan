# WebSocket、Push 与降级

## 1. 在线优先

前台活跃设备优先使用 WebSocket。

## 2. 后台与离线

当 WebSocket 不可达时：

- 使用系统 Push 做唤醒提示
- 设备恢复后走 sync API 补拉

## 3. 降级路径

1. WebSocket 正常：实时 hint
2. WebSocket 断开：Push 提示
3. Push 未达：客户端启动后自行 gap fill

## 4. 约束

- Push 只发提示，不发完整 patch
- 客户端不得仅依赖 Push 保证一致性
