# cross-domain-search-journey 任务列表

> 任务顺序：metadata → codegen → 业务逻辑 → 测试 → gate → 交付
> 状态标记：[x] 已完成 / [ ] 待完成

## 当前交付任务

- [x] T1: 冻结 `_shared` route/surface/request context 与四域 `Search*` contract 的 metadata 真相源 → J1 J2
- [x] T2: 重跑 `verify-metadata`、`codegen`、`codegen-app`，建立搜索 route、DTO 与 assistant handoff 的 codegen 基线 → J1 J2 J3
- [x] T3: 落地 route-driven `GlobalSearchPage` 与首页/聊天/圈子/助手四个统一入口 → J1
- [x] T4: 落地 `SearchCoordinator`、统一结果模型、四域 fan-out、局部降级与结果跳转 → J2
- [x] T5: 落地 recent search 本地+云同步、语音 ASR 转词与问小趣 typed handoff → J1 J3
- [x] T6: 执行 analyze / widget tests / `make gate`，验证整版发布与回滚口径 → J1 J2 J3 R1

## 搁置任务（带规划）

- [ ] P1: 搜索结果排序策略与召回权重统一治理
- [ ] P2: 弱网与异常场景下的线上指标看板自动化

## 未来演进任务

- [ ] F1: 全局搜索推荐词、热搜与个性化入口
- [ ] F2: 搜索结果页的服务端聚合与分页优化
