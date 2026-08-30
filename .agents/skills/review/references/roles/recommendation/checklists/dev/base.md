# recommendation · dev

- [MUST] 行为上报与云侧事件契约同源，四类反馈能关联请求与策略版本。
  evidence: recommendation-event-contract
- [MUST] 冷启动与结果坍缩有可执行检测和回滚阈值。
  check: 读取指标与 rollback 判据；缺可计算阈值时判失败。
- [MUST NOT] 用 fixture、数据库 seed 或派生投影预填构造验证数据。
  check: 读取验证输入来源；命中任一禁止形态时判失败。
