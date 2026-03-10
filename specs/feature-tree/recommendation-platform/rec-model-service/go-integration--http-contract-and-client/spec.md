# L5 叶子：http-contract-and-client

Go 与模型服务集成最小可交付单元：ModelPredictRequest 增加 Scenario；HTTPModelServiceClient 实现并传 scenario；content-service 配置与 CascadeScorer 组装；失败回退 RuleScorer。

## 验收

- A1：启用时调用模型服务；关闭或失败时 RuleScorer。A3：超时失败时回退。A7：契约与 Python 一致。A8：客户端与 CascadeScorer 有测试。
