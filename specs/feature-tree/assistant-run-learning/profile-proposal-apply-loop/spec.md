# L2 特性：profile-proposal-apply-loop

## 功能说明
- 定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
- 保障助手建议以“可审核、可回滚”的方式进入用户资料系统。

## 约束
- 提案状态流转必须强一致并具备幂等控制。
- 调用方只提交命名意图与稳定 `Idempotency-Key`，不提交 proposal version。
- 应用路径固定为 `confirmed -> applying -> applied|expired`：`applying` 是持久化检查点，
  会阻断并发拒绝；Persona 写入按 `proposalId` 幂等，进程重启可安全续作。
- 目标 Persona version 是提案确认时保存的服务端内部快照，仅用于防止把旧提案覆盖到
  已发生新修改的 Persona，不进入公开请求或响应。
- 所有提案操作必须产生日志审计与追踪标识。

## 验收标准
- A1：提案创建、确认/拒绝、应用路径可用。
- A6：敏感字段处理符合隐私与审计要求。
- A8：状态机与回滚用例自动化测试通过。
