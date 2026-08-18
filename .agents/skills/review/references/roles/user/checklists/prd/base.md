# user · prd · base

你在 prd 的唯一任务：把需求当成一条要走的路，找出走不通的地方。

## PRE 准入

- [MUST] 主路径每一步都有明确入口与出口，没有「然后用户就到了 X」这类跳步
  check: 逐步走一遍需求描述；存在无法说明如何到达的步骤，判失败
- [MUST] 失败与中断路径已定义：网络失败、权限拒绝、数据为空、未登录各自的表现
  check: 只定义了成功路径，判失败
- [MUST] 涉及账号态入口时，「关闭 / 稍后」的安全落点与「登录成功」的目标态都已写出
  check: 只写登录成功路径，或关闭后回到会再次触发登录的状态，判失败
- [SHOULD] 首次使用体验已考虑：空数据、新账号、无历史时页面仍可理解
- [SHOULD] 能力不可用时的降级体验已定义（无相机、无 RTC、离线）

## DURING 执行中

- [MUST NOT] 用「后续迭代补」来跳过失败态定义；要么定义，要么显式判 Out of Scope
  check: 存在既未定义、也未判 Out of Scope、也未转 `OPEN-###` 的失败态，判失败

## POST 自检

- [MUST] 登录入口无死循环契约成立（本次触及登录入口时）
  gate: make verify-app-login-entry-loop-contract
- [SHOULD] Journey 动作声明完整
  gate: make verify-app-journey-action-declaration

## HANDOFF 交接

- 产出：主路径步骤清单、失败/中断路径清单、登录入口的双目标定义
- 未决项去向：暂不支持的降级路径转 `OPEN-###`，写明用户会看到什么
- 下一步：`design`，其 PRE 需要本次的失败路径清单
- 证据链：上述 gate 的实际输出
