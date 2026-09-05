# 接手、重做与新 execution

本文件不是恢复状态机；只给宿主 AI 解释 producer create-once facts 的规则。

| 磁盘事实 | AI 动作 |
| --- | --- |
| 仅有 `task init` 三文件，无 receipt | 从 `0.plan` OPEN 开始 |
| 最新 producer 阶段 CLOSE 为 `pass` 且不是 `release` | 按 `SKILL.md` 固定顺序进入后继 |
| 某 producer 阶段 OPEN 在场、CLOSE 缺失 | 读取 OPEN 冻结的 exact inputs，在同一 execution 重做该阶段，然后 POST/CLOSE |
| 最新 producer 阶段 CLOSE 为 `blocked` | 停止该 execution；保留 typed issues；以新 executionId 重新 `task init` |
| receipt/result ref 缺失或摘要漂移 | blocked；不得修补旧 receipt 或业务证据 |
| 所有 release execution 的 sequence-009 CLOSE pass，terminal handoff 缺失 | 调用窄 `release handoff` writer create-once 物化；不得提前标记 END |
| terminal handoff create-once 成功且只读复核通过 | 交给下游环境 owner；producer 到 `END` |

blocked 后禁止在原 execution rewind、覆盖输入、补写旧结果或推导恢复阶段。新 execution 可在 manifest 中显式引用前一次 execution 作为审计背景，但不得兼容或复用 sequence-017，也不得把旧状态迁入新 receipt。

环境 import/activate/readback/UAT/EAF 的失败或成功不改变以上 producer 规则；环境重试、rollback 与 replay 由下游 owner 基于 release handoff 独立处理。
