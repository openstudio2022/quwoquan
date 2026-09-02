# 接手与恢复判定

任何宿主、任何新会话接手一个已存在的 `.qwq_output/data/tasks/<executionId>/`
工作包时，按本表从磁盘事实定位断点。**不猜测失败原因，不依赖会话记忆。**

## 接手步骤

1. 读 `execution_manifest.json` 与 `_shared/execution_state.json`。
2. 列 `_shared/receipts/`，按 `sequence` 取最新 receipt。
3. 对照下表决定下一动作；进入目标阶段前先做该阶段契约的做前（PRE）段复验。

## 判定表

| 磁盘事实 | 下一动作 |
| --- | --- |
| 无 `_shared/receipts/` 或目录为空 | 工作包已由 `task init` 原子创建时从 `0.plan` 契约开始；三文件缺失则 `GATE_BLOCK` |
| 最新 receipt `verdict=pass` 且 `next≠END` | 进入 `next` 指向的阶段 |
| 最新 receipt `verdict=pass` 且 `next=END` | execution 已完成；只做只读核验，不得再写 |
| 最新 receipt `verdict=blocked` | 读 `typedIssues`：按唯一 `recoveryStage` 新建 retry execution；无法安全恢复则 typed GATE_BLOCK 并停 |
| `execution_state.status ∈ {succeeded, superseded}` | 终态保护：**不可 resume**，见下 |
| receipt 与磁盘产物矛盾（PRE 复验失败） | 以磁盘复验结果为准，落 `verdict=blocked` receipt 说明矛盾，报告用户 |
| 存在活跃 claim（心跳未过 TTL，见 [orchestration.md](orchestration.md)） | 不接手；另选 execution 或等待 |

## 同 ID resume 条件

同一 `executionId` 只允许 resume：未达终态、无活跃 claim、receipt 链与磁盘一致。
resume 即按上表进入断点阶段，重复执行同一阶段是幂等安全的（做前复验 + create-once receipt）。

## 终态保护与重试

`succeeded` / `superseded` 不可 resume、不可改写。需要新尝试时创建**新的
executionId**（同前缀 sequence+1，命名见 [execution-layout.md](execution-layout.md)），
经已实现的 `task init` 原子创建新工作包后，从 [`0.plan` 契约](stage-contracts/0.plan.md)重新开始，并在新工作包的 `execution_manifest.json` 声明
`retryOf: <原 executionId>`。重试没有第二条路径。

- [MUST NOT] 经由旧编排入口（`task execute`、pool-dispatch/campaign 等自动推进状态机）重试；
  重试唯一路径是上述「新 executionId + `0.plan`」。
- [MUST NOT] 手写阶段产物、补写缺失的 source/rights/review/release 证据。
- [MUST NOT] 创建平行状态根或第二任务身份。
- 失败必须保留明确的阶段与原因，不得迁移、兼容或伪造通过。

## 核验命令

```bash
python3 quwoquan_data/scripts/cli.py verify content-execution-layout --execution-id <id>
python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id <id>
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
```
