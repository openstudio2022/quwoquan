---
name: /dev
id: dev
category: Development
description: 实现已冻结 Story/能力并闭环验证，实现期执行可测试性、读写分离、领域与前端规范自检
---

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

实现期自检（落位前逐项确认）：

- **可测试性**：新逻辑可从 canonical 测试树观察（导出 API 或对象级 typed port）；不得为可测性发明 test-only 后门。横切区（`runtime/internal/tools/cmd`）旁路同包测试必须以 `__local_contract_test` 层后缀命名，api_integration 禁止旁路同包。
- **读写分离**：新增消费入口只依赖对象级 `*CommandWriter/*Query` typed port；禁止聚合 Repository、动态 Filter/Map 或为展示路径加载 aggregate（裁决口径同 `/extend` Command/Query 分流）。
- **领域与服务规范**：服务侧遵循 DDD 依赖方向与对象边界，跨对象只依赖 port/事件；边界冲突回 `/design`，不在实现里就地发明。
- **前端规范**：触及 `quwoquan_app/lib` 时按 `quwoquan_app/AGENTS.md` 与 `.cursor/rules/02-dart-coding.mdc` 自检——设计系统 token、i18n/UITextConstants、响应式断点、iOS 语义；Provider/Widget 测试以 `sealedCloudBoundaryOverrides()` 开头，禁止新增聚合 Mock 替身（棘轮只减不增）。
- **失败处理**：测试红先归因四选一（`本计划引入 / 并行会话中间态 / 存量债 / 环境 flaky`），并行中间态不修不掩盖、如实交接。

出口按 Exit Review 报告规格达成、测试、E2E、产品/UX、质量与观测、门禁和剩余 OPEN。未运行的验证必须说明原因；失败不得包装为通过。

自然语言等价触发："实现""修复""开始写代码"。
