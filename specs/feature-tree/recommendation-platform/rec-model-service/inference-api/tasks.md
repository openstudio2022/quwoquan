# 开发任务：inference-api（L4）

- [ ] FastAPI 应用：main.py、POST /v1/score、GET /health
- [ ] 请求校验与 scenario 路由：api/score.py
- [ ] 各 scenario 模型加载与推理：models/content_feed.py（必选），circle_discovery/friend_suggestion（可选占位）
- [ ] 特征解析：features/transformer.py 与 feature_registry 对齐
- [ ] ModelRegistry 同步：从 OSS/本地拉取 production 模型
- [ ] 接口测试：/v1/score 与 /health 自动化测试
