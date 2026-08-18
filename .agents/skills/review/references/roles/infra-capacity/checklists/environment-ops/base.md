# infra-capacity · environment-ops · base

成本口径见 [cost-model](../../references/cost-model.md)。

## POST 自检

- [MUST] 放量前确认目标环境容量满足预估峰值，并写明依据（当前水位 + 增量预估）
  check: 放量决定无容量数据支撑，判失败
- [MUST] 回滚版本的资源占用已确认可承载，回滚不受容量阻塞
  check: 回滚路径依赖已释放或已缩容的资源，判失败
- [SHOULD] 本次环境变更的成本增量已按 cost-model 口径估算

## HANDOFF 交接

- 产出：容量核对结论与成本增量估算
- 未决项去向：容量缺口转 `OPEN-###` 并标注阻断的放量 step
- 下一步：放量推进由 environment-ops 工作流承接
- 证据链：水位数据来源
