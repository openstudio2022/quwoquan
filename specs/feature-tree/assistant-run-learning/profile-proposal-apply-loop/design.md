# profile-proposal-apply-loop 设计

## 设计动因

小趣从对话中识别出的用户偏好/资料改进建议，必须经用户显式确认才能进入资料治理，不允许静默改写用户画像。本 L2 定义提案对象的状态机闭环：生成 → 审阅 → 确认/拒绝 → 应用落档 → 版本化审计。

## 状态机

```
proposed ──confirm──> confirmed ──apply──> applying ──> applied
   │──reject──> rejected                        │──fail──> expired(可重试)
   └──timeout──> expired
```

- 状态迁移由用户命令驱动（confirm/reject），应用阶段由服务端异步执行并版本化记录。
- `confirmed→applying→applied|expired` 迁移必须原子；应用失败可重试，不产生半应用状态。
- 提案与应用结果都关联源 run/turn，可回溯「为什么小趣提出这个建议」。

## 对象边界

- 提案对象归 assistant 域；应用目标（Persona 资料字段）归 user 域，应用经 user 域 public command 完成，不直连其存储。
- 审计事实 append-only；撤销 = 生成反向提案再走同一状态机，不做原地回滚。

## 非功能

- 提案生成不阻塞 run 主链（旁路 best-effort）；确认/拒绝命令 p95 300ms；应用幂等（提案 id 为幂等键）。
