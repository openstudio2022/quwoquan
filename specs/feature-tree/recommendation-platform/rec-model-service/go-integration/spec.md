# L4 对象任务：go-integration（与 Go 业务服务集成）

## 功能说明

- **契约**：ModelPredictRequest 增加 Scenario 字段（或 Context 中携带）；Go 与 Python 双端一致。
- **Go 客户端**：HTTPModelServiceClient 实现 ModelServiceClient；请求 /v1/score 时传入 scenario（content-service 传 content_feed）；超时与重试可配置。
- **兜底**：CascadeScorer 在模型服务不可用或超时时回退到 RuleScorer；content-service 通过配置启用/禁用模型调用。

## 实现要点

- scorer.go 中 ModelPredictRequest 增加 Scenario；RemoteModelScorer 已通过 client.Predict 调用，无需改接口签名，仅请求体扩展。
- content-service config 增加 rec_model_service.url、timeout、enabled；main.go 组装 HTTPModelServiceClient 与 CascadeScorer。
- 可选：content_feed 的 Go 本地 leaves 推理路径，与 Remote 二选一由配置控制。

## 约束

- 不破坏现有 RuleScorer 与 Engine 行为；模型关闭时行为与当前一致。
- 契约变更需双端同步（Go 请求体、Python 解析）。

## 验收标准

- A1：content-service 启用 rec_model_service 时，GetFeed 使用模型打分；关闭时使用 RuleScorer。
- A3：模型服务不可用时 CascadeScorer 回退，请求不失败。
- A7：契约与 Python 端一致。
- A8：HTTPModelServiceClient 与 CascadeScorer 有单元或集成测试。
