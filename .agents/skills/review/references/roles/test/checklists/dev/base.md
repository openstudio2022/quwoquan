# test · dev · base

## PRE 准入

- [MUST] 已拿到 design 的分层映射表，知道本次要补哪一层的哪些用例
  check: 无映射表且本次新增对外行为，判失败
- [SHOULD] 已确认先写会失败的测试（红），再实现

## DURING 执行中

- [MUST NOT] 用动态 skip、放宽断言或删断言让红转绿；缺依赖如实报阻塞
  gate: make verify-test-no-fake
- [MUST NOT] `api_integration` 用裸 HTTP、自 seed、Memory adapter 或动态 skip 冒充证据
  gate: make verify-test-no-fake
- [MUST NOT] `user_acceptance` 用 fixture-only journey 或路径存在性断言冒充通过
  gate: make verify-test-no-fake
- [MUST NOT] 把失败门禁包装为成功，或用「已知问题」掩盖本次引入的失败
  check: 每个「已知问题」必须有基线对照证据（HEAD 重跑或 `git log --follow`）；
  无证据的归因，判失败

## POST 自检

- [MUST] 三层映射成立
  gate: make verify-test-coverage-map
- [MUST] 无伪测试
  gate: make verify-test-no-fake
- [MUST] 测试目录分层合规
  gate: make verify-test-directory-layout
- [MUST] 错误码断言覆盖（本次触及错误链路时）
  gate: make verify-error-code-assertion-coverage
- [MUST] 质量维度覆盖达标
  gate: make verify-quality-axis-coverage
- [SHOULD] 非功能覆盖达标
  gate: make verify-test-nonfunctional-coverage

## HANDOFF 交接

- 产出：新增测试文件路径与其绑定的验收锚点、测试执行结果汇总
  （通过/失败/跳过各多少，跳过的原因）
- 未决项去向：未覆盖的锚点转 `OPEN-###`，标注准出影响（`block` 还是 `track`），不得留白
- 下一步：POST 评审汇总
- 证据链：全部 gate 输出，**失败项必须原样列出**
