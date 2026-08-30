# data-quality · dev

- [MUST] 变更保留 source-to-manifest 身份与 typed stage failure。
  evidence: data-static-contract
- [MUST] 重试、恢复与发布不覆盖历史有效产物。
  check: 读取写入/恢复路径；原地改写历史 release 或 receipt 时判失败。
- [MUST NOT] 用 fixture 或直接 seed 冒充环境内容证据。
  check: 读取环境装配与证据来源；命中 fixture/seed 时判失败。
