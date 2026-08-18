# developer · dev · dart-app

适用：改动触及 `quwoquan_app/**` 的 Dart 代码。
真相源：[dart](../../references/dart.md)、
[result-state-semantics](../../references/result-state-semantics.md)。

## DURING 执行中

- [MUST NOT] `catch` 之后 `return null` 当作结果且不留证据。两条合法出路：
  解析器用 `try` 前缀命名承诺「返回 null 表示这不是一个 X」；故障降级必须留痕
  （`recordHandledException`、显式失败态，或 `developer.log(error:)`）
  gate: python3 quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py
- [MUST NOT] 用可空返回类型表达失败。`T?` 只允许表达缺席
  gate: python3 quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py
- [MUST NOT] 让必填字段在缺失时解码成功，或补入契约未声明的默认值
  gate: python3 quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py
- [MUST NOT] 非可空列表返回 null；默认 `const []`
  gate: python3 quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py
- [MUST NOT] 业务层 `import 'dart:io'`；文件/路径能力走 `FileStorageGateway`
  gate: make verify-app-page-horizontal-quality

## POST 自检

- [MUST] 失败/缺席语义隔离通过
  gate: python3 quwoquan_app/scripts/runtime/observability/verify_null_failure_isolation.py
- [MUST] 吞异常预算未超
  gate: make verify-app-catch-swallow-budget
- [MUST] 生产代码未引入测试符号
  gate: make verify-app-lib-test-only-symbols

## HANDOFF 交接

- 产出：Dart 侧改动文件清单与失败语义处理点
- 未决项去向：临时降级实现转 `OPEN-###`
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出
