# developer · dev

- [MUST] 改动落在 PRE owner identity 指定的对象与契约边界内。
  check: 对照 changed_paths 与 plan.contexts；存在越界写入或无 owner 路径时判失败。
- [MUST NOT] 吞异常、把失败伪装成缺席/空值，或为错误实现增加 fallback。
  check: 逐个读取新增判失败路径；catch 后无 typed failure/观测或返回零值时判失败。
- [MUST NOT] 为单一实现造框架、复制规范事实或手改生成物。
  check: 读取新增抽象、文档与生成 diff；命中任一形态时判失败。
- [MUST] 命名、注释与测试失败能直接指向业务语义。
  check: 读取新增命名/注释/断言消息；只表达阶段或复述代码时判失败。

本 checklist 不拥有 gate；Reviewer 只消费 Board 已执行的 evidence。
