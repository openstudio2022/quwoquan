# content-action-intent-contract 设计（8 类反馈闭环）

## 设计动因

当前反馈链路存在“局部可用、全局不闭环”问题：

1. 端侧多处反馈入口已接入，但不同动作走不同路径，语义不统一。
2. 推荐热链路（HotPath Redis）主要吃 batch 行为，专用路由反馈没有统一桥接策略。
3. 计数与推荐信号混杂：推荐可变，计数未必同步落库。
4. `block keywords` 缺少明确业务字段，导致 UI 有入口但缺持久化对象。

## 目标态架构

```
UI Feedback (8 actions)
  -> Intent/Repository boundary
    -> A. Batch behavior route (/v1/content/behaviors)
         actions: impression/click/dwell/share/dislike
    -> B. Dedicated routes
         like/favorite/comment/report/block user/block keywords
  -> content-service / user-service persistence
  -> recommendation hot path + feed filtering + counters reconciliation
```

## 关键设计决策

### 决策 1：动作分层不混用（已定）

- Batch 行为：`impression/click/dwell/share/dislike`
- 专用路由：`like/favorite/comment/report`
- 用户域反馈：`block user/block keywords`

理由：batch 强调吞吐和实时，专用路由强调幂等、审计和计数一致性。

### 决策 2：`report` 路由统一到举报实体服务（本次基线修正）

- `behaviors.yaml` 中 `report.dedicated_route` 统一为 `POST /v1/content/reports`
- 避免与不存在的 `/v1/content/posts/{postId}/report` 冲突。

### 决策 3：`block keywords` 归属 UserSetting（本次基线新增）

- 在 `UserSetting` 增加 `blockedKeywords` 字段（string[]）。
- 由用户设置接口统一读写，内容/推荐只消费该偏好做过滤。

### 决策 4：计数链路与推荐链路解耦但可对账（实施期完成）

- 推荐实时：Redis session state（TTL）
- 业务计数：主存储计数字段（like/favorite/comment/share/view）
- 通过契约测试约束“同一动作同时满足推荐与计数”。

### 决策 5：A7 采用“召回后过滤”接入 user block + keyword block（本次交付落地）

- 过滤阶段位置：`Engine.GetFeed` 召回后、打分前（post-filter）。
- 过滤输入：
  - `blocked user`：`X-Blocked-User-Ids`（逗号分隔）或 `blockedUserIds` query。
  - `blocked keywords`：`X-Blocked-Keywords`（逗号分隔）或 `blockedKeywords` query。
- 过滤命中范围：`authorId`、`title/body/tags`（关键词大小写不敏感子串匹配）。
- 选择理由：不改变召回组件契约，先以最小侵入保证闭环；后续可由网关把 user-service 设置自动注入请求上下文。

## 方案对比

### 方案 A（选定）：基于现有节点 update 扩容

- 在 `content-action-intent-contract` 节点追加 8 类反馈闭环范围。
- 同步必要 metadata（字段 + 路由语义）后再进入交付。

优点：路径最短，能复用既有测试与节点上下文。  
缺点：节点范围扩大，任务拆分需更细。

### 方案 B：新建独立 L4 节点

- 新建 `eight-feedback-closed-loop` 子节点单独推进。

优点：边界更清晰。  
缺点：当前上下文已沉淀在本节点，迁移成本更高。

## 选型结论

采用**方案 A（update）**：先完成 metadata 基线对齐，再在 `/opsx-deliver` 按 8 类动作分批实施。
