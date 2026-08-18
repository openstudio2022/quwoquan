# growth · design · base

承接原 `/obs-plan` 的准入：观测点、SLO、告警、回滚条件必须在实现前冻结。

## PRE 准入

- [MUST] 观测点已冻结：要埋哪些事件、每个事件的维度与口径
  check: 观测点未定却已进入实现计划，判失败
- [MUST] SLO 已冻结：指标名、目标值、统计窗口
  check: 缺任一项判失败
- [MUST] 告警已冻结：触发条件、通知对象、对应处理路径
  check: 告警只写「异常时通知」而无阈值或处理路径，判失败
- [MUST] 回滚触发条件已冻结：哪个指标越过哪个值就回滚
  check: 无量化触发条件，判失败
- [SHOULD] 已声明采样率与保留期
- [SHOULD] 指标支持必要的维度切分（surface、内容类型、来源）而不是只有总量

## DURING 执行中

- [MUST NOT] 先实现再补观测声明
  check: 对照 design 的 HANDOFF；实现已落地但观测点仍未冻结，判失败
- [MUST NOT] 让埋点语义与 metadata 中的 `event` / `metric` 定义分叉
  gate: make verify-observability-catalog

## POST 自检

- [MUST] 观测目录一致
  gate: make verify-observability-catalog
- [MUST] 错误码与恢复语义对齐
  gate: make verify-service-error-recovery-alignment
- [SHOULD] 契约告警覆盖成立
  gate: make verify-contract-alert-overlay

## HANDOFF 交接

- 产出：冻结后的观测点、SLO、告警与回滚条件
- 未决项去向：暂不可观测的能力转 `OPEN-###`，写明盲区范围
- 下一步：`dev`，其 PRE 需要本次冻结的观测点清单
- 证据链：上述 gate 输出
