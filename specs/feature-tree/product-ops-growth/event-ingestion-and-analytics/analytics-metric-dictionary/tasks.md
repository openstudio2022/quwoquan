# 开发任务：analytics-metric-dictionary

## 阶段 0：字典冻结
- [ ] 冻结九大指标域、公共维度、业务维度、对标映射与下钻路径
- [ ] 明确每个指标的分子/分母、采样策略、默认聚合粒度、训练资格

## 阶段 1：metadata / 配置对齐
- [ ] 评估是否将指标字典 metadata 化
- [ ] 若 metadata 化，补齐生成规则与消费位置
- [ ] 对齐 dashboard / query / feature projection 所需字段命名

## 阶段 2：实现与接入
- [ ] 建立事件 -> 指标条目映射表
- [ ] 建立最小 dashboard / query 消费契约
- [ ] 确保推荐、Assistant、运营共享同一指标口径

## 阶段 3：测试与 gate
- [ ] unit/contract：指标口径、维度与兼容性校验
- [ ] integration：同一事件在多消费者中的指标一致性
- [ ] gate 验证
