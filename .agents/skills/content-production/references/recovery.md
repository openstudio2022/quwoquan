# 接手、重做与新 execution

本文件不是恢复状态机；只给宿主 AI 解释 create-once facts 的规则。

| 磁盘事实 | AI 动作 |
| --- | --- |
| 仅有 `task init` 三文件，无 receipt | 从 `0.plan` OPEN 开始 |
| 最新阶段 CLOSE 为 `pass` | 按 `SKILL.md` 固定顺序进入下一阶段 |
| 某阶段 OPEN 在场、CLOSE 缺失 | 读取 OPEN 冻结的 exact inputs，在同一 execution 重做该阶段，然后 POST/CLOSE |
| 最新阶段 CLOSE 为 `blocked` | 停止该 execution；保留 typed issues；以新 executionId 重新 `task init` |
| receipt/result ref 缺失或摘要漂移 | blocked；不得修补旧 receipt 或业务证据 |
| ship CLOSE pass | 只读核验完成证据，不再写该 execution |

blocked 后禁止在原 execution rewind、覆盖输入、补写旧结果或推导 recovery stage。新 execution 可在 manifest 中显式引用前一次 execution 作为审计背景，但不得兼容或复用 sequence-017，也不得把旧状态迁入新 receipt。
