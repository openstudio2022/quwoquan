# L3 子特性：works-unified-feed

## 功能说明

新增服务端混排统一 works-feed API 端点，替代当前三路独立 feed（`images`/`video`/`article`）。服务端负责三类精品内容的交替排序，客户端通过 `filter_type` 参数筛选，共用同一 cursor 分页。

## 范围

- 新增 `GET /v1/content/works-feed` 端点到 `contracts/metadata/content/service.yaml`
- 端侧新增 `ContentRepository.listWorksFeedPage(filterType, cursor, limit)` 方法
- `WorksFeedProvider`（Riverpod AsyncNotifier）：管理 works-feed cursor 分页状态
- `filter_type` 枚举：`null`（全部）/ `image` / `video` / `article`
- 响应类型：`CursorPage<PostBaseDto>`，沿用现有 `postBaseDtoFromMap()` 多态派发

## 适用范围与约束

- **适用**：作品频道所有三类媒体（美图/视频/文章）；`filter_type` 筛选切换时 cursor 重置
- **不适用**：微趣（moment）使用独立 category；推荐排序算法逻辑由后端实现
- **约束**：
  - 端点必须先在 `service.yaml` 声明，`make verify` → `make codegen` 后方可编写 Repository
  - Remote 实现必须使用 `CloudRuntimeConfig.gatewayBaseUrl`，禁止硬编码 URL
  - Mock 实现必须覆盖三类 DTO（至少各 2 条混排样本）

## 与父/子节点关系

- **父**：`dual-rail-discovery-redesign`（L2）
- **依赖**：`feed-item-dto-contract`（FeedItemDto/PostBaseDto 已 codegen）
- **被依赖**：`works-immersive-viewer` 的 `WorksFeedProvider` 依赖本节点输出

## 验收标准概要

- A1：`service.yaml` 中 works-feed 端点定义存在，`make codegen` 生成对应 Repository 方法签名
- A2：Mock 实现返回三类 DTO 混排，`postBaseDtoFromMap()` 正确派发类型
- A3：`filter_type=image` 只返回 `PhotoPostDto`；`filter_type=null` 返回混排
- A4：cursor 分页：第二页 cursor 正确，追加到现有列表末尾，不重复
- A5：Remote 实现使用正确端点路径和 `CloudRequestHeaders.forPage('works.feed')`
