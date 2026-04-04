# 开发任务：event-ingestion-and-analytics

## 阶段 0：contracts-first / 设计冻结
- [x] 审核并冻结 `spec.md / design.md / acceptance.yaml / plan.yaml / CR`
- [x] 对齐竞品吸收结论、SLO/KPI、容量/成本、生命周期、灰度/回滚
- [x] 明确统一事件字典、schema 治理、学习桥接的单一真相源
- [x] 将商用 blocker 映射到 acceptance / CR：`VisitRecord` 契约漂移、page access 本地-only、T3/T4 真实验证

## 阶段 1：metadata 对齐
- [ ] 盘点受影响 metadata：统一 event ingestion、visit 聚合、learning events、share/entity/social/rtc 相关契约
- [ ] 新增统一 event ingestion metadata，并收口 `VisitRecord` 为聚合/体验标签职责
- [ ] 补齐 `contracts/metadata` 中的字段、错误码、route/surface/operation 与 storage 定义
- [ ] 执行 `make -C quwoquan_service verify-metadata`
- [ ] 执行 `make codegen`
- [ ] 执行 `make codegen-app`

## 阶段 2：端侧统一 reporter 与高优先级事件接入
- [ ] 为 page access / perf 接入统一 event ingestion reporter（仅保留必要本地 fallback）
- [ ] 为 analytics façade 接入统一 ingress，不再仅映射成 `visit_record`
- [ ] 为 content behavior 补 `eventId / experimentBucket / entity / shareTarget` 等字段与失败重试
- [ ] 为 Assistant learning 准备真实 cloud sync adapter 入口
- [ ] 明确 `AnalyticsService` 的收口方式（统一 reporter façade）

## 阶段 3：云侧接入与存储分层
- [ ] 实现 product-ops 统一 event ingestion 与 visit 聚合服务
- [ ] 保持 Redis hot path 与 Mongo serving 向后兼容
- [ ] 建立统一事件读模型/查询面，支撑页面访问、analytics、learning、visit 复盘
- [ ] 建立学习特征投影与运营查询最小闭环

## 阶段 4：反馈应用闭环
- [ ] 推荐：在线反馈 -> 热特征 -> 重排/过滤
- [ ] Assistant：InteractionEvent / Scorecard -> 聚合 -> 注入
- [ ] 运营：指标字典 -> dashboard/query -> 实验复盘

## 阶段 5：测试与 gate
- [ ] mock/unit/contract/integration/uat 分层补齐
- [ ] 将 `test/core/**` 纳入默认 gate
- [ ] 验证 schema 幂等、采样/背压、冷热分层与隐私策略
- [ ] 强制 T3 staging 合同验证，不再以未配置 skip 为通过口径
- [ ] 补齐 T4 Patrol/FTL 旅程：弱网、回放、实验切桶、回滚
- [ ] 执行 `make gate`
- [ ] 执行 `make gate-full`
