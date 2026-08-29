# test · dev · service

- [MUST] 每个 typed port 和对象行为映射正确的三层证据。
  evidence: service-object-evidence
- [MUST] slice 字段、顺序、分页、空态与失败均有具体断言。
  check: 读取新增 query 测试；只断言非空或漏任一状态时判失败。
- [MUST NOT] 用 in-memory double 替代真实存储集成证据。
  check: 读取 api_integration 装配；存储被 double 替换时判失败。
