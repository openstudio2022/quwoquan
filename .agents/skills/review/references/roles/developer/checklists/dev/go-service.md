# developer · dev · go-service

适用：改动触及 `quwoquan_service/services/**` 的 Go 代码。
真相源：[result-state-semantics](../../references/result-state-semantics.md)。

## DURING 执行中

- [MUST NOT] 用 `nil` / 零值同时表达「缺席」与「失败」；失败必须走 error 返回
  gate: make verify-service-nil-semantics
- [MUST NOT] 用 `omitempty` 让必填字段在缺失时静默通过；必填缺失必须 fail-closed
  gate: make verify-service-nil-semantics
- [MUST NOT] 错误码硬编码字符串；只使用 codegen 产物中的 `MODULE.KIND.REASON` 常量
  gate: make verify-emitted-error-code-declaration

## POST 自检

- [MUST] 服务侧 nil 语义隔离通过
  gate: make verify-service-nil-semantics

## HANDOFF 交接

- 产出：Go 侧改动文件清单与失败语义处理点
- 未决项去向：临时降级实现转 `OPEN-###`
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出
