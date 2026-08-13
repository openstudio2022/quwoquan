---
name: /continue-dev
id: continue-dev
category: Development
description: 持续执行规格就绪、开发、验证、闭环复核、下一轮的循环
---

# /continue-dev

目标：持续执行"规格就绪 → 开发 → 验证 → 闭环复核 → 下一轮"的循环。

场景 A（规格就绪）：运行 feature context，确认父链、设计归属、验收和 OPEN 后，按 `/dev` + `/verify` 实施。

场景 B（上一轮结束）：先按 `/plan-next` 完成闭环复核——计划对账、失败归因四选一、环境与门禁健康、缺口与风险三选一裁决、闭环判定；已解决 OPEN 转为规格，未解决 OPEN 保留在最低 owner，棘轮残量只减不增；再生成当前会话计划并回到场景 A。

硬约束：metadata-first；不引入第二真相源、v1/v2 并存、shim、fallback、allowlist、弱类型穿透、空 catch、手改 codegen 或 UI 直连 Mock；测试失败或环境阻断先归因（本计划引入 / 并行会话中间态 / 存量债 / 环境 flaky）再报告一次真实原因，不循环重述计划。

所有长期信息只在 spec/design/metadata/code/test 中；不创建中央 backlog、任务台账、changelog 或状态矩阵。出口使用根 `AGENTS.md` 的 Exit Review。

自然语言等价触发："继续开发""按规划实施""复盘后接着做"。
