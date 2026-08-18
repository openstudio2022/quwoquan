# test · prd · base

## POST 自检

- [MUST] 每条验收锚点（UAT/DOM/SIT/GWT/contract）都能被一个真实测试绑定
  check: 逐条锚点指出它将由哪一层（`local_contract` / `api_integration` /
  `user_acceptance`）的什么测试覆盖；指不出且无 `OPEN-###`，判失败
- [MUST] 验收断言可判定：写明输入、预期输出与失败表现，不接受「体验良好」类模糊表述
  check: 锚点无法翻译为可执行断言，判失败
- [SHOULD] 错误路径与空态与成功路径同权重出现在验收中

## HANDOFF 交接

- 产出：验收锚点 → 证据层的初始映射
- 未决项去向：暂无法绑定的锚点转 `OPEN-###`
- 下一步：`design` 或 `dev`，其 PRE 需要本映射
- 证据链：映射表本身
