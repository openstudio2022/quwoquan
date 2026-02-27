# works-unified-feed 任务清单

## 当前交付任务

- [ ] **M1** 在 `contracts/metadata/content/service.yaml` 中新增 `works-feed` 端点（GET，query params: filter_type / cursor / limit）
- [ ] **C1** `make verify` 通过 → `make codegen` → `make codegen-app`
- [ ] **R1** `ContentRepository` 新增 `listWorksFeedPage({filterType, limit, cursor})` 抽象方法
- [ ] **R2** `MockContentRepository` 实现：返回三类 DTO 混排 mock 数据（各 ≥ 2 条），`filter_type` 筛选正确
- [ ] **R3** `RemoteContentRepository` 实现：调用 `/v1/content/works-feed`，使用 `CloudRuntimeConfig.gatewayBaseUrl` + `CloudRequestHeaders.forPage('works.feed')`
- [ ] **P1** 新建 `WorksFeedNotifier`（`lib/ui/discovery/providers/works_feed_provider.dart`）：`load(filterType)` / `appendNextPage()`；`filterType` 变更重置 cursor
- [ ] **T1** Contract test：works-feed 响应包含三类 DTO 且 `postBaseDtoFromMap()` 正确派发
- [ ] **T2** Unit test：`WorksFeedNotifier.load(filterType='image')` 只含 `PhotoPostDto`
- [ ] **T3** Unit test：`appendNextPage()` 追加到列表末尾，不重复，cursor 更新

## 搁置任务（带规划）

暂无。

## 未来演进任务

- [ ] 推荐排序信号接入（依赖 `feed-orchestration-recommendation/personalized-ranking`）
- [ ] A/B 实验参数支持（`experiment_id` query 透传）
