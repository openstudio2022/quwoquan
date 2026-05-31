# /dev

目标：实现已冻结 Story，并闭环验证。

准入：
- Story `spec.md` 与 `acceptance.yaml` 已稳定。
- 所属业务能力 `design.md` 覆盖实现约束。
- 当前工作能指出 UAT/SIT/GWT/contract 与 T1~T4。

执行：
1. 读取相关 spec/design/acceptance、registry、CR。
2. 审视 metadata/codegen、seed、mock、权限、生命周期、观测、回滚。
3. 从 Story acceptance 与当前会话计划派生 todo。
4. Red → Green → Refactor。
5. 回填测试证据并运行触发范围门禁。

阻断：不得以部分端、部分测试或无证据状态停止。
