# /prune

目标：清理废弃或取消的特性树节点与增量记录。

准入：
- 已确认 AppRoot Journey/Scenario、领域服务、业务能力、Story 不再需要该增量。
- 无已发布接口、数据迁移、seed、测试、路由或文档仍依赖它。
- Git diff 与动态 change report 能证明删除范围及唯一 owner。

动作：删除空节点、废弃验收、无引用 fixture 和失效引用；已发布行为仍需要时必须保留为当前规格，不能改写成历史兼容记录。

禁止：删除仍被 metadata、测试、路由、页面矩阵或发布批次引用的节点。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/prune` 语义执行；执行前仍需按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
