# test · prd

- [MUST] 每条验收可映射到 local_contract、api_integration 或 user_acceptance 的真实测试。
  evidence: feature-tree
- [MUST] 空、缺席、失败与恢复终态有可判定断言。
  check: 逐条读取 GWT；状态合并或无法断言时判失败。
- [MUST NOT] 用路径存在、动态 skip 或 fixture-only journey 充当完成判据。
  check: 读取验收完成判定；命中任一伪证据形态时判失败。
