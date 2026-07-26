# /continue-dev

目标：持续执行“规格就绪 → 开发 → 验证 → 复盘 → 下一轮”的闭环。

场景 A（规格就绪）：运行 feature context，确认父链、设计归属、验收和 OPEN 后，按 `/dev` + `/verify` 实施。

场景 B（上一轮结束）：先按 `/verify` 如实复盘；已解决 OPEN 转为规格，未解决 OPEN 保留在最低 owner；再按 `/plan-next` 形成当前会话计划并回到场景 A。

硬约束：metadata-first；不引入第二真相源、v1/v2 并存、shim、fallback、allowlist、弱类型穿透、空 catch、手改 codegen 或 UI 直连 Mock；测试失败或环境阻断只报告一次真实原因，不循环重述计划。

所有长期信息只在 spec/design/metadata/code/test 中；不创建中央 backlog、任务台账、changelog 或状态矩阵。出口使用根 `AGENTS.md` 的 Exit Review。

自然语言等价触发：“继续开发”“按规划实施”“复盘后接着做”。
