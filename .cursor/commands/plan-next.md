# /plan-next

目标：完成一轮开发后先诚实复盘，再基于节点 OPEN 与新用户价值生成下一轮会话计划。

执行：

1. 按 `/verify` 对照父链验收与真实测试结果，判定已达成/部分/未达成/回归风险。
2. 已解决事项删除 OPEN 并成为当前规格；未完成事项放在最低 owner 节点 OPEN，不能用下一轮计划遮盖。
3. 运行 `make feature-tree-overview` 和 `make feature-tree-change-report` 获取风险/规划总览与本轮影响。
4. 下一轮计划写在当前会话，包含目标、规格增量、实施任务、验收锚点、测试层、质量门与退出条件；不创建 tracked tasks、plan 或 changelog。

本轮仍有无证据完成声明、测试失败、未归属变更或 `OPEN block` 时返回 `GATE_BLOCK`，不得宣称已进入下一轮开发。

自然语言等价触发：“下一轮做什么”“完成后再规划”“生成后续计划”。
