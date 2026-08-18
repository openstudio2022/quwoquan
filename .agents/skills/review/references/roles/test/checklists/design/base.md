# test · design · base

design 你只判一件事：**这个设计能不能被测**。可测性是设计属性，不是事后写测试能补救的。

## PRE 准入：可测试性

- [MUST] 每条验收锚点（`UAT / DOM / SIT / GWT / contract`）都能被三层测试之一直接绑定
  check: 逐条读验收锚点；存在无法映射到任一层的锚点，判失败
- [MUST] 被测决策可经导出 API 或对象级 typed double 观察
  check: 若观察某个决策必须依赖未导出符号、test-only 后门或 fixture 注入，判失败
- [MUST] 三层归属已明确：哪些锚点进 `local_contract`、哪些进 `api_integration`、
  哪些进 `user_acceptance`
  check: 未分层或全部堆在一层，判失败
- [SHOULD] 失败可归因：测试失败时的报错能指向具体契约条目或规则，而不只是断言不等

## DURING 执行中

- [MUST NOT] 为了让设计可测而在生产代码开测试后门、暴露 test-only 符号
  gate: make verify-app-lib-test-only-symbols
- [MUST NOT] 用 fixture 注入替代真实 command/event 构造测试前置
  gate: make verify-app-mock-isolation

## POST 自检

- [MUST] 验收锚点与测试的映射成立
  gate: make verify-test-coverage-map
- [MUST] 测试目录分层合规
  gate: make verify-test-directory-layout
- [SHOULD] 非功能覆盖已声明
  gate: make verify-test-nonfunctional-coverage

## HANDOFF 交接

- 产出：验收锚点到三层测试的映射表、需要新建的测试文件路径
- 未决项去向：暂时不可测的锚点转 `OPEN-###`，写明缺什么能力才可测
- 下一步：`dev`，其 PRE 需要本次的分层映射表
- 证据链：上述 gate 的实际输出
