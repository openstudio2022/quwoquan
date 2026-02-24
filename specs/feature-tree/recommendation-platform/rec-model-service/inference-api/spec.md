# L4 对象任务：inference-api（多场景推理 API）

## 功能说明

- **入口**：POST /v1/score，请求体含 scenario、userId、sessionId、userFeatures、sessionSignals、candidates、context；响应体含 scores 数组（id、score、detail）。
- **路由**：按 scenario（content_feed、circle_discovery、friend_suggestion）选择模型与特征解析器；id 对应 contentId、circleId 或 userId。
- **模型加载**：从 ModelRegistry 或本地/OSS 加载各 scenario 的 production 模型；支持热加载或定期同步。
- **推理**：LightGBM 批量预测；特征转换与 feature_registry 对齐。

## 实现要点

- FastAPI 应用；/health 健康检查。
- 各 scenario 独立模型文件与特征解析模块；未支持 scenario 可返回 501 或规则分兜底。
- 延迟目标满足 Go 侧预算。

## 约束

- 请求/响应与 Go ModelPredictRequest/ModelPredictResponse 契约一致。
- 仅读特征与模型，不写业务数据。

## 验收标准

- A1：POST /v1/score scenario=content_feed 返回正确 scores。
- A2：推理延迟满足约定。
- A7：契约与 Go scorer 一致。
- A8：推理 API 有接口测试。
