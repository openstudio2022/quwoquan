# /explore

目标：只读澄清增量归属，不写代码。

准入：
- 用户需求尚未明确一棵树归属、验收意图、证据层或触发规则。
- 只读探索，不改代码、不改文档、不运行破坏性命令。

执行：
- 读取 `AGENTS.md`、`docs/agent_context_contract.md` 和相关 spec/registry。
- 形成 `Spec Entry`，但不进入实现。
- 标注需要继续 `/prd`、`/design`、`/baseline`、`/extend` 或 `/dev` 的条件。

必须输出：
- AppRoot Journey/Scenario：`<id 或无影响>`
- `L1_domain_service`：`<domain>`
- `L2_business_capability`：`<capability>`
- `L3_story`：`<story 或需新建>`
- 验收意图：UAT / SIT / GWT / contract
- 测试证据：T1 / T2 / T3 / T4
- metadata、seed、mock、页面质量、runtime error、发布风险

出口：
- 给出通过/阻断结论。
- 若阻断，列出缺失的规格、验收、设计或测试证据。
- 若可继续，明确下一阶段命令。

阻断：无法定位树归属、验收或测试证据时返回 `GATE_BLOCK`。

自然语言等价触发：用户说“先看看”“帮我分析归属”“这个需求怎么拆”“风险是什么”时，也按 `/explore` 语义执行。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
