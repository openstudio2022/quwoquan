# /dev

目标：实现已冻结 Story/能力并闭环验证。

准入：`make feature-context TARGET=<target>` 可得到唯一父链；L3 REQ/GWT 与设计归属稳定；父 L2 SIT、L1 DOM 和受影响 AppRoot UAT 可追踪；相关 `OPEN block` 已明确处置。

执行：

1. 按根 `AGENTS.md` 完成 Spec Entry 与 Pre-work Reflection。
2. 读取父链、相关 DEC、metadata 和对应测试，不扫描整棵树。
3. 从 REQ/GWT/SIT/UAT 与当前会话计划派生 todo；不创建 tracked task/plan。
4. metadata-first → verify/codegen → Red → Green → Refactor。
5. Remote/API 断言必须在 local_contract 的 Mock/Provider/Widget/领域规则中有对应覆盖；用户旅程变化补 user_acceptance。
6. 若实现发现规格或设计冲突，停止并回到 `/prd` 或 `/design`，不得让代码反向定义规格。
7. 运行影响面测试、`make verify-feature-tree` 和 `make feature-tree-change-report`。

出口按 Exit Review 报告规格达成、测试、E2E、产品/UX、质量与观测、门禁和剩余 OPEN。未运行的验证必须说明原因；失败不得包装为通过。

自然语言等价触发：“实现”“修复”“开始写代码”。
