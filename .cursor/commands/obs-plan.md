# /obs-plan

可观测方案冻结入口。

产出必须绑定：
- 一棵树归属。
- 用户可见症状和运营指标。
- SLI/SLO、告警阈值、采样、保留周期。
- local_contract 配置静态、local_contract 模块埋点、api_integration 端云链路、user_acceptance 旅程观测证据。

不产出正式树内计划文档。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/obs-plan` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
