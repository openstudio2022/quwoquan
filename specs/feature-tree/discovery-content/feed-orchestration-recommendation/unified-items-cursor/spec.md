# L3 特性：unified-items-cursor

## 功能说明
- 细化 unified-items-cursor 特性的功能边界与端云协同行为。

## 约束
- 契约与字段策略必须与 OpenAPI 与 metadata 保持一致。
- feed 查询快照必须遵守 `runtime-client-foundation/local-cache-architecture`，对象策略以 [`object-cache-policy.yaml`](../../../runtime/runtime-client-foundation/local-cache-architecture/object-cache-policy.yaml) 中 `QuerySnapshot` 为准。
- query key 由 `surfaceId + querySignature + cursor/filter/sort` 组成；snapshot 只保存对象 id 列表、cursor、排序与 fetchedAt，不保存弱类型远端原始响应。
- feed item 对应的 post/user/media 数据必须进入对象缓存，query snapshot 不复制对象本体。
- 一级/二级 tab 切换时应先恢复最近成功 snapshot，再后台刷新；离线启动可展示最近 snapshot 并标识离线状态。
- 用户清理离线内容或浏览记录时可删除 query snapshot，但不得删除仍被收藏、关注、最近会话引用的对象本体。

## 验收标准
- A1：功能路径可执行且输出稳定。
- A7：契约一致性校验通过。
- A8：对应自动化测试映射完整。
- A9：feed query snapshot 支持 stale-while-revalidate、离线回显、tab 切换不重复拉取，并在清理离线内容后按策略删除。
