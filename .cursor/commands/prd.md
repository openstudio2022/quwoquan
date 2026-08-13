---
name: /prd
id: prd
category: Specification
description: 更新当前有效规格与可测试的验收锚点，不做实现
---

# /prd

目标：更新当前有效规格与验收，不做实现。

准入：`/explore` 已明确目标父链、用户价值、范围和关键依赖。

执行：

1. 按 `specs/feature-tree/README.md` 更新对应 `spec.md`。
2. AppRoot 写 Journey/Scenario/UAT；L1 写领域边界/REQ/DOM/工程归属；L2 写能力范围/REQ/SIT；L3 写独立价值/REQ/GWT。
3. 跨域 Journey 只在 AppRoot 写完整叙事，参与节点写自身职责和反向链接。
4. 未完成能力、阻断、风险或未来规划写到最低可关闭节点 `OPEN-###`；完成项直接成为当前 REQ，不保留完成状态。OPEN 完成判定必须引用验收锚点，否则结构上不可裁定。
5. 字段、path、operation、surface、route、error、event、metric 只引用 metadata ID。
6. 验收只保留改变产品契约的代表场景；测试排列组合、路径、命令和结果留在测试代码/运行输出。
7. 每条 GWT/SIT 必须可被三层测试直接绑定：GIVEN 可注入、WHEN 可触发、THEN 可断言且经导出面或对象级 typed port 观察；写不出观察方式的验收先改写，不留给实现阶段发明旁路。
8. 运行 `make verify-feature-tree` 与 `make feature-tree-change-report`。

产出只有目标父链的 `spec.md`，以及确有设计变化时的上层设计输入；不创建 acceptance、registry、index、changelog、任务台账或成熟度矩阵。

权限、生命周期、异常恢复、SLO、灰度回滚、canonical metadata 未明确或验收不可测试绑定时返回 `GATE_BLOCK`。

自然语言等价触发："写 PRD""冻结需求""明确规格/范围/验收"。
