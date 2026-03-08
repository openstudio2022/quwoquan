# 任务拆解（端云一体）

## 云侧（quwoquan_service）
- [ ] contracts：更新 OpenAPI + contracts 文档
- [ ] specs：补齐场景与约束
- [ ] tasks：在 `quwoquan_service/tasks.md` 增加本特性任务（引用 §0 全服务统一能力）
- [ ] 实现：DDD 分层 + 复用 `runtime/*`
- [ ] 测试：单测 + 契约测 + 集成测

## 端侧（quwoquan_app）
- [ ] 页面/数据源迁移：Repository mock/remote 一键切换
- [ ] RemoteRepository：严格按 contracts 解码（items/nextCursor）
- [ ] headers：统一注入（pageId 三段式命名）
- [ ] 测试：单测/集成（必要时加 mock server）

## 门禁
- [ ] 本地：`make gate`
- [ ] CI：required checks 全绿

