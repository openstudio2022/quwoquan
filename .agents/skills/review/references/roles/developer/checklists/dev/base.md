# developer · dev

- [MUST] 改动落在 PRE owner identity 指定的对象与契约边界内。
  check: 对照 changed_paths 与 plan.contexts；存在越界写入或无 owner 路径时判失败。
- [MUST NOT] 吞异常、把失败伪装成缺席/空值，或为错误实现增加 fallback。
  check: 逐个读取新增判失败路径；catch 后无 typed failure/观测或返回零值时判失败。
- [MUST NOT] 为单一实现造框架、复制规范事实或手改生成物。
  check: 读取新增抽象、文档与生成 diff；命中任一形态时判失败。
- [MUST] 命名、注释与测试失败能直接指向业务语义。
  check: 读取新增命名/注释/断言消息；只表达阶段或复述代码时判失败。

- [MUST NOT] 一个变更单元混入无关职责、穿透对象边界直连存储或增加仅有单一使用点的无行为包装层。
  check: 读取具体新增 path/symbol、调用边与契约依据；命中无关职责、存储穿透或无行为包装时判失败，无可定位事实不发 finding，不生成 SOLID 分数。
- [MUST] replacement 声明按 canonical `candidate_review_closure` 留有旧入口、接替入口、消费者迁移、实现/配置/测试清理或保留依据及扫描/测试证据。
  check: 读取 replacement 声明与命名扫描/测试 evidence；有替换却缺入口、消费者或清理依据时判失败，动态入口 unknown 却自动删除时判失败。无替换不要求删除清单，机器字段/引用验证不等于语义证明。

本 checklist 不拥有 gate；Reviewer 只消费 Board 已执行的 evidence。

- [MUST] 消费当前 candidate 的 canonical Code Health Delta，不重跑、不以主观判断覆盖 terminal。
  evidence: code-health-delta
  check: 客观输入仅为 current candidate 的 changed paths、candidate fingerprint，以及 report 绑定的 changed paths、fingerprint 与 terminal。evidence 缺失、report 未绑定这些输入、report fingerprint/changed paths 与 current candidate 不一致（stale），或 terminal 为 `GATE_BLOCK` 时判失败；terminal 为 `PR_WARN` 时，只有逐项裁决并证实为本轮 fix-now 已修复、最低 owner `OPEN` 或有边界证据的 out-of-scope 才可通过，漏裁决时判失败。主审在现有 result 的 `candidate_closure` 按原始 `findingId` 写唯一 typed disposition，绑定 current candidate fingerprint；fix-now 须绑定后续健康验证且原 findingId warning 不再有效（同一 immutable candidate 确定性重跑不能消除告警，源码修复须新 candidate），OPEN 必须当前最低 owner 存在且有完成判定，out-of-scope 必须能证明 path 与 owner 均在 candidate 外。高风险 blocker 不可用 OPEN 抵消。
