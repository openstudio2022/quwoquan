# L3 Story：cross-session-fatigue-memory

## 功能说明

把端侧真实曝光 `impressed` 从 session 级短记忆升级为用户级跨会话滚动窗口，并用时间衰减表达“看过但可在未来恢复”的疲劳语义。

## 范围

- `impressed` per-user 滚动窗口，按 `user+day` 分桶跨会话保持。
- `negative` 改为用户级 key（修复当前绑 sessionId 导致跨会话失效），与 `hidden_authors/types` 对齐。
- 过滤路径用 membership 点查或近似结构，禁止长窗口全量 `SMembers`。
- 疲劳惩罚随时间衰减，而不是永久屏蔽。
- 强负反馈优先级高于疲劳惩罚。
- 不同用户活跃度可配置窗口长度。

## 非目标

- P0 不引入 Bloom/Cuckoo 或精确 Sorted Set；先用 user+day bucket 与候选 membership 点查闭合中小规模容量路径。
- 不改变 H2 hidden author/type 的强过滤语义。

## 验收标准

- A1：真实 impressed 是疲劳和训练信号，served 不是训练正样本。
- A2：疲劳窗口和半衰期来自 recpolicy。
- A3：跨会话重复曝光率可由 `repeat_exposure_rate` 观测。
- A4：疲劳过强导致候选不足时可降级为软降权。
- A5：`impressed` 按 `user+day` 分桶跨会话保持，`negative` 改用户级 key，二者过滤均不依赖长窗口全量 `SMembers`。
