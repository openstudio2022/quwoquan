# architect · design

- [MUST] 对象边界、command/query 分流与依赖方向有唯一裁决，可从 PRE owner identity 直达。
  check: 读取 plan.contexts 与目标 DEC；缺唯一 owner/anchor 或只有结论没有裁决依据时判失败。
- [MUST] 契约和设计各自只拥有本层事实，不复制字段、错误或功能约束。
  check: 对本次新增事实反查 contracts 与 Feature；同一事实有两个可写 owner 时判失败。
- [MUST NOT] 引入第二真相源、兼容双轨、手改生成物或绕过 typed port。
  check: 读取 diff 与 codegen 输出；命中任一形态时判失败。
- [MUST] 失败恢复、观测与回滚能被真实测试或命名 evidence 证明。
  evidence: feature-tree
