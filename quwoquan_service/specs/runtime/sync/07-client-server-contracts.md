# Sync 客户端与服务端契约

## 1. 客户端感知模型

客户端只感知：

- 是否有新变化
- 从哪个 `afterSeq` 开始拉
- 当前拿到的 patch 列表

客户端不需要感知：

- 服务端内部事件总线
- MQ 拓扑
- 对象存储实现

## 2. 实时通知格式

建议最小化：

```json
{
  "type": "sync_hint",
  "userId": "u_1",
  "latestSyncSeq": 12345
}
```

## 3. 增量拉取接口

建议统一形态：

```json
{
  "afterSeq": 12000,
  "limit": 200
}
```

返回：

```json
{
  "patches": [],
  "latestSyncSeq": 12345,
  "hasMore": false
}
```

## 4. 错误处理

- cursor 过旧：允许回补
- limit 超限：返回参数错误
- patch 过多：分页返回

## 5. 客户端本地策略

- 顺序消费 patch
- 幂等跳过旧 `syncSeq`
- 批量刷新 UI
