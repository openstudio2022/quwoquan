# /plan-review

目标：开发前从产品、UX、架构、代码、测试、用户、运维、运营八角色审核当前会话计划与规格父链；不写实现。

逐角色检查：独立用户价值与范围；Journey/父子责任；owner/DDD/metadata 单轨；主路径/边界/失败/并发；页面四态与平台体验；三层测试；SLO/告警/灰度/回滚；自动门禁与变更归属。

不符合项只能：当前增量补入对应 spec/design/metadata/测试计划；作为最低 owner 节点 OPEN；或明确 Out of Scope。禁止创建任务清单、changelog、成熟度矩阵或中央风险台账。

输出 `满足 / 待补 / 阻断`，每项指向具体 REQ/GWT/SIT/DOM/UAT/DEC/OPEN 或当前会话任务。通过后进入 `/baseline`、`/extend` 或 `/dev`；方案分叉退回 `/prd` + `/design`。

自然语言等价触发：“开发前评审”“规划是否完整”“多角色看遗漏”。
