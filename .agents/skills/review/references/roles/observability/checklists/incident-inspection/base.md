# observability · incident-inspection · base

## DURING 执行中

- [MUST] 异常按 fingerprint 分组统计，不逐条罗列原始日志
  check: 报告出现未聚合的重复异常条目，判失败
- [MUST] 每个结论附可复查的查询语句或链接（ES query、dashboard、trace id）
  check: 结论无法凭报告内信息复查，判失败

## POST 自检

- [MUST] 新增告警声明阈值、去噪策略与 owner；不允许无人认领的告警
  check: 告警定义缺 owner 或阈值依据，判失败
- [SHOULD] 巡检发现的观测盲区（缺指标、缺日志字段、缺告警）已转 `OPEN-###`

## HANDOFF 交接

- 产出：fingerprint 分组报告与查询链接
- 未决项去向：观测盲区转 `OPEN-###`
- 下一步：修复走 `dev`，观测补齐走 `dev` 或 `design`
- 证据链：查询语句与报告
