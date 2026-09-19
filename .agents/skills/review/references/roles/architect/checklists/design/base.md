# architect · design

- [MUST] 对象边界、command/query 分流与依赖方向有唯一裁决，可从 PRE feature context 直达。
  check: 读取 plan.contexts 与目标 DEC；缺关联 context/anchor 或只有结论没有裁决依据时判失败。
- [MUST] 契约和设计各自只拥有本层事实，不复制字段、错误或功能约束。
  check: 对本次新增事实反查 contracts 与 Feature；同一事实有两个可写 owner 时判失败。
- [MUST NOT] 引入第二真相源、兼容双轨、手改生成物或绕过 typed port。
  check: 读取 diff 与 codegen 输出；命中任一形态时判失败。
- [MUST NOT] 形成可定位的依赖环、对象私有存储穿透、无行为的单使用点抽象或无迁移边界的第二配置真相源。
  check: 读取具体 path/symbol、依赖方向及 DEC/contract；命中依赖环、私有存储穿透、无行为抽象或第二配置源时判失败，不以主观 SOLID 分数裁决。
- [MUST] 声明 replacement 时说明旧入口、接替入口、消费者迁移及实现/配置/测试退役或保留依据。
  check: 按 canonical `candidate_review_closure` 读取 replacement 与当前扫描/测试证据；声明替换却缺证据或 unknown 动态入口自动删除时判失败。无替换不虚构删除清单，结构化字段通过不替代行为等价判断。
- [MUST NOT] 新增 DEC、类型或公开 API 名把可变闭集的当前基数写成身份。
  check: 读取新增名称及其成员来源；基数进入标识符，或成员集合脱离唯一 canonical 声明源另立平行表时判失败，冻结协议 id 与契约字面量除外。
- [MUST] 失败恢复、观测与回滚能被真实测试或命名 evidence 证明。
  evidence: feature-tree
