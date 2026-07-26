# /rec-audit

推荐审计入口。

检查：树归属、UAT/SIT/GWT/contract、三层测试、指标漂移、冷启动、偏置、召回覆盖、归因链、AB 分桶、回滚阈值。

输出按严重程度列 findings；不把审计结果写成新的树层级。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/rec-audit` 语义执行；执行前仍需按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
