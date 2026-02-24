# L5 叶子：scenario-router-and-models

## 功能说明

多场景推理的最小可交付单元：根据请求体 scenario 路由到对应模型与特征解析器，加载 production 模型并执行批量预测，返回与 Go 契约一致的 scores。当前必选 content_feed；circle_discovery、friend_suggestion 可占位。

## 验收标准

- A1：POST /v1/score scenario=content_feed 返回正确 scores；其他 scenario 可 501 或占位。
- A7：请求/响应与 ModelPredictRequest/ModelPredictResponse 一致。
- A8：有 /v1/score 的接口测试。
