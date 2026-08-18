# developer · dev · base

## PRE 准入

- [SHOULD] 改动落点已确定，不是「先写再看放哪」
- [SHOULD] 已确认要复用的现有能力，而不是并行造第二套

## DURING 执行中

- [MUST NOT] 稳定路径、schema key 或测试标识使用 `t1..t4 / m6 / phase0 / partN` 等阶段名
  gate: make verify-retired-terms-zero
- [MUST NOT] 写复述代码的注释。注释只解释代码无法表达的意图、取舍与约束
  check: 逐条读新增注释；删掉它不丢失任何信息（如「// 增加计数」「// 返回结果」），判失败
- [MUST NOT] 用失败降级为 `null` / 空集合 / 零值的方式表达错误；四态模型见
  [result-state-semantics](../../references/result-state-semantics.md)
  check: 逐个失败路径确认落在「在场有值 / 在场为空 / 缺席 / 失败」之一且不混淆
- [SHOULD NOT] 为单一实现造接口，或为一次性逻辑建框架

## POST 自检

- [MUST] 阶段名残留为零
  gate: make verify-retired-terms-zero

## HANDOFF 交接

- 产出：改动文件清单、新增的失败语义处理点
- 未决项去向：临时降级实现必须转 `OPEN-###`，写明何时收口
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出
