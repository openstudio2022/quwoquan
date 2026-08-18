# user · dev · flutter-page

## PRE 准入

- [MUST] 已拿到 prd 的失败/中断路径清单
  check: 无清单且本次改动触及用户可见流程，判失败

## DURING 执行中

- [MUST NOT] 强入口允许 `pop` 回受限状态；强入口必须 `allowGuestDismissPop: false`
  gate: make verify-app-login-entry-loop-contract
- [MUST NOT] 只传 `dismissFallback` 却允许 `pop` 回触发点——这会形成
  「关闭登录页 → 回到受限状态 → 再次弹登录」死循环
  gate: make verify-app-login-entry-loop-contract
- [MUST NOT] 把错误码或异常原文直接呈现给用户
  gate: make verify-app-recoverable-error-surface
- [MUST NOT] 能力缺失时崩溃或白屏；必须返回结构化不可用并降级
  check: 对每个新增平台能力依赖，构造能力不可用路径；出现崩溃、白屏或静默空页，判失败
- [SHOULD NOT] 让用户在没有下一步动作的错误页里终止

## POST 自检

- [MUST] 登录入口无死循环
  gate: make verify-app-login-entry-loop-contract
- [MUST] 可恢复错误有对应界面与恢复动作
  gate: make verify-app-recoverable-error-surface
- [MUST] 端云错误语义一致
  gate: make verify-app-error-endcloud-parity
- [SHOULD] 原生边缘导航行为正确
  gate: make verify-app-native-edge-navigation

## HANDOFF 交接

- 产出：本次覆盖的失败态与恢复动作、登录入口改动点
- 未决项去向：未实现的降级路径转 `OPEN-###`
- 下一步：POST 评审汇总，其 PRE 需要失败态的可测入口
- 证据链：上述 gate 的实际输出
