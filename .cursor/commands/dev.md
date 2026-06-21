# /dev

目标：实现已冻结 Story，并闭环验证。

准入：
- Story `spec.md` 与 `acceptance.yaml` 已稳定。
- 所属业务能力 `design.md` 覆盖实现约束。
- 当前工作能指出 UAT/SIT/GWT/contract 与 三层测试。

执行：
1. 读取相关 spec/design/acceptance、registry、CR。
2. 按 `docs/agent_context_contract.md` 做正向规格理解与执行前自检反思。
3. 对照 `docs/agent_command_simulation_matrix.md` 确认自然语言输入对应的命令阶段、禁止事项和出口证据。
4. 审视 metadata/codegen、seed、mock、权限、生命周期、观测、回滚。
5. 从 Story acceptance 与当前会话计划派生 todo。
6. Red → Green → Refactor。
7. 回填测试证据并运行触发范围门禁。
8. 完成后按测试、E2E、产品/UX、运营观测、自动化/门禁、剩余风险复盘，不得只列改动文件。

出口：
- 输出 `Exit Review`：规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁、剩余风险。
- 明确未跑验证的原因。
- 若发现规格/验收缺口，停止并退回 `/prd`、`/design` 或 `/plan-review`。

阻断：不得以部分端、部分测试或无证据状态停止。

自然语言等价触发：用户说“实现一下”“修这个问题”“开始写代码”时，也按 `/dev` 语义执行；若规格或验收不清，先退回 `/explore`、`/prd` 或 `/plan-review`。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
