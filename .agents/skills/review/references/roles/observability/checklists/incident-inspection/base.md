# observability · incident-inspection

- [MUST] 异常按 fingerprint 聚合，结论附可复查查询与时间范围。
  check: 读取报告；重复逐条罗列或缺 query/time range 时判失败。
- [MUST] 日志和 trace 已脱敏，原始敏感载荷不进入报告。
  check: 扫描报告样本；出现 token/凭据/完整 PII 时判失败。
- [MUST] 复现资格、优先级与 owner 有证据，不由单条样本推断。
  check: 读取每组裁决；缺样本量、影响面或 owner 时判失败。
- [SHOULD] 观测盲区进入最低可关闭节点的 OPEN。
