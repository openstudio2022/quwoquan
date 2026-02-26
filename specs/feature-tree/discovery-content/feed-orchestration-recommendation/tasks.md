# 开发任务：feed-orchestration-recommendation

## 总览
- [x] contracts-first
- [x] metadata 对齐
- [ ] 实现（部分完成，见下）
- [ ] 测试（mock/unit/contract/integration/uat）
- [ ] gate 验证

---

## 基于端侧反馈的实时推荐链路（端云打通）

### 云侧（content-service + runtime）

| # | 任务 | 状态 | 说明/位置 |
|---|------|------|-----------|
| 1 | GET /v1/content/feed 支持 userId/sessionId 并调用推荐引擎 | ✅ | `content_handler.handleGetFeed` → `resolveUserID/resolveSessionID` → `FeedService.ListFeed` → `engine.GetFeed` |
| 2 | POST /v1/content/behaviors 接收端侧行为并写入 HotPath | ✅ | `handleReportBehaviors` → `BehaviorService.ProcessBatch` → `hotPath.ProcessSignalBatch`；契约见 `generated_routes.go` |
| 3 | 推荐引擎 RecordImpression（本次下发 item 列表） | ✅ | `runtime/recommendation/engine.go` 在 GetFeed 返回后异步 `feedback.RecordImpression` |
| 4 | 文章详情打开时服务端侧 impression 信号 | ✅ | `PostService.GetPost` 内 `signaler.ProcessSignal(impression)`（见 `post_service.go`） |

### 端侧（quwoquan_app）

| # | 任务 | 状态 | 说明/位置 |
|---|------|------|-----------|
| 5 | Feed 请求携带 sessionId（与行为上报同 session） | ✅ | `CloudRequestHeaders.forPage()` 含 `X-Client-Session-Id`；`listDiscoveryFeed` 使用同一 headers，服务端 `resolveSessionID(r)` 从 Header 读取 |
| 6 | BehaviorRepository 三层 + Remote 对接 POST /v1/content/behaviors | ✅ | `lib/cloud/services/behavior/behavior_repository.dart`：Abstract/Mock/Remote；Remote 用 `CloudRuntimeConfig.gatewayBaseUrl` + `CloudRequestHeaders.forPage('content.behavior.report')`，body 含 `sessionId` |
| 7 | 文章详情页：曝光 + 停留 + 点赞/收藏 上报 | ✅ | `article_detail_page.dart`：加载成功后 `reportSingle(impression)`；`deactivate` 时 `reportSingle(dwell)`；点赞/收藏按钮 `reportSingle(like|favorite)` |
| 8 | 发现页：点击、分享等互动上报 | ✅ | `discovery_page.dart`：`_trackBehavior` 注入 `_MomentPostCard` 的 `onBehavior`；`_trackBehavior('click'|'share', post)` |
| 9 | **发现流列表项曝光（impression）上报** | ❌ | 发现流内 item 进入视口时未上报 impression；需在列表（微趣/美图/视频/文章）可见时批量或按需调用 `behaviorRepository.reportEvents(events: [BehaviorEvent(..., action: 'impression')])`，与 feed session 一致 |

### 端云一致性

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 10 | 行为 action 与云侧 supportedBehaviorActions 一致 | ✅ | 端：impression/click/dwell/like/favorite/share/dislike/report；云：`behavior_service.go` 同集合 |
| 11 | sessionId 在 feed 与 behaviors 间一致 | ✅ | 端侧均用 `CloudRequestHeaders.sessionId`（单次启动稳定），feed GET 带 Header、behaviors POST 带 body+Header |

### 待办（补齐）

- [ ] **任务 9**：实现发现流（微趣/美图/视频/文章 tab）列表项曝光上报：在卡片进入视口时（如 `VisibilityDetector` 或列表 onVisibility 回调）调用 `BehaviorRepository.reportEvents`，action=impression，contentId/tags 与当前 post 一致，避免重复上报（如 500ms 内同 contentId 只报一次）。
- [ ] 为 feed-orchestration-recommendation 补充 mock/unit/contract 测试映射（见 `acceptance.yaml`）并执行 gate。

---

## 四类内容全量用户反馈实施方案

> 四类：文章(article)、微趣(moment)、美图(photo)、视频(video)。反馈：关注作者、赞、收藏、转发、评论、不感兴趣、不想看此作者、不想看此类内容、举报。详见 `design.md`。

### 阶段一：契约与云侧扩展

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| F1 | 行为请求体扩展 authorId、contentType | ❌ | contracts/metadata 或 OpenAPI：events[].authorId、events[].contentType 可选；BehaviorEventInput 与端 BehaviorEvent 对齐 |
| F2 | 新增 action：comment, follow, hide_author, hide_content_type | ❌ | behavior_service supportedBehaviorActions；HotPath SignalWeights（comment 2.0, follow 1.5） |
| F3 | Redis 键 rec:hidden_authors:{userId}、rec:hidden_types:{userId} | ❌ | redis_keyspace.yaml 登记；HotPath 实现 addHiddenAuthor、addHiddenType，GetSessionState 读出 HiddenAuthorIDs、HiddenContentTypes |
| F4 | SessionState 增加 HiddenAuthorIDs、HiddenContentTypes | ❌ | runtime/recommendation：SessionState 结构体与 GetSessionState 填充 |
| F5 | Engine Stage 4 按作者/类型过滤 | ❌ | 过滤 candidate.AuthorID ∈ HiddenAuthorIDs 或 ContentType ∈ HiddenContentTypes |
| F6 | BehaviorSignal 增加 AuthorID、ContentType 字段 | ❌ | runtime/recommendation/hotpath.go；ProcessSignal 中 hide_author/hide_content_type 分支 |

### 阶段二：端侧扩展与回调对接

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| F7 | BehaviorEvent 与 reportSingle 支持 authorId、contentType | ❌ | lib/cloud/services/behavior/behavior_repository.dart；toJson 与 Abstract 方法签名 |
| F8 | 不感兴趣 → 上报 dislike | ❌ | media_post_card _handleNotInterested：reportSingle(contentId, 'dislike', tags: [contentType 或 post.tags]) |
| F9 | 不喜欢该作者 → 上报 hide_author | ❌ | media_post_card _handleBlockUser：reportSingle(contentId, 'hide_author', authorId: post 作者 id)；可选调 user block API |
| F10 | 不想看此类 / 屏蔽词 → 上报 hide_content_type | ❌ | more_action_popup 屏蔽词 onTap：reportSingle(contentId, 'hide_content_type', contentType: post.type)；或提供「此类内容」选项 |
| F11 | 举报 → 上报 report | ❌ | media_post_card _handleReport：reportSingle(contentId, 'report')；可选调 POST /v1/content/reports |
| F12 | 关注作者 → 上报 follow | ❌ | 卡片/详情关注按钮：user-service 关注 API（若有）+ reportSingle(contentId, 'follow', authorId: authorId) |
| F13 | 评论成功 → 上报 comment | ❌ | 评论提交成功回调中 reportSingle(contentId, 'comment') |

### 阶段三：四类内容统一与测试

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| F14 | 发现流四类卡片统一走同一套更多菜单与 BehaviorRepository | ❌ | 微趣/美图/视频/文章均能触发不感兴趣、不喜欢该作者、不想看此类、举报；post.type 与 contentType 枚举一致 |
| F15 | 契约测试：hide_author / hide_content_type 写入与 GetFeed 过滤 | ❌ | 验证 ProcessSignal(hide_author) 后 GetSessionState 含 HiddenAuthorIDs；GetFeed 不返回该作者内容 |
| F16 | 端侧 MockBehaviorRepository 可记录 authorId、contentType | ❌ | 测试与集成时校验上报 payload |

### 实施顺序建议

1. **F1 → F2 → F6 → F3 → F4 → F5**：契约与云侧先闭环（隐藏作者/类型过滤可测）。
2. **F7**：端侧契约扩展，与 F1 对齐。
3. **F8～F13**：端侧各入口接好上报（不感兴趣/不喜欢作者/此类/举报/关注/评论）。
4. **F14～F16**：四类统一校验与测试、gate。

---

## /qwq-extend 扩展场景映射

> 依据 `specs/runtime_extension_catalog.md`，将任务映射到扩展场景或手动契约更新。ReportBehaviors 为 content-service 已有 API，行为事件请求体非独立实体，故多为契约/配置扩展。

### 可映射的扩展场景

| 任务 | 扩展场景 | 说明 |
|------|----------|------|
| F15 | **S20** add-test | 已有实体（content/post 域）新增契约测试场景：hide_author / hide_content_type 写入与 GetFeed 过滤。`qwq add test --entity=post --scenario=behavior_hide_author_filter` 或等价。 |
| — | — | 其他任务见下方「契约与手写」 |

### 契约与手写更新（无对应 S01–S20）

| 任务 | 更新路径 | 文件 |
|------|----------|------|
| F1 | OpenAPI 扩展 BehaviorEvent  schema | `contracts/openapi/content-service.v1.yaml`：BehaviorEvent 增加 authorId、contentType 可选字段 |
| F1 | 共享类型扩展 | `contracts/metadata/_shared/types.yaml`：BehaviorEventType 增加 comment, follow, hide_author, hide_content_type |
| F1 | post/service 描述更新 | `contracts/metadata/post/service.yaml`：ReportBehaviors 的 description 补充新 action |
| F3 | Redis 键登记 | `contracts/metadata/_shared/redis_keyspace.yaml`：新增 rec:hidden_authors、rec:hidden_types  pattern |
| F2,F4,F5,F6 | 云侧手写 | behavior_service.go、hotpath.go、engine.go、SessionState |

### 执行顺序（metadata-first）

```
① 更新 contracts：OpenAPI BehaviorEvent + types.yaml + redis_keyspace.yaml + post/service.yaml
② make verify
③ 云侧手写：BehaviorService、HotPath、Engine、BehaviorSignal
④ 端侧手写：BehaviorEvent、reportSingle、各回调
⑤ S20（若有）：add-test 或手动在 contract_test 中新增 scenario
⑥ make test-contract && make gate
```

### 特性树子节点（可选）

若将「四类内容全量反馈」拆为独立 L3 便于追踪，可在 feed-orchestration-recommendation 下新增：

```
feed-orchestration-recommendation (L2)
  └── content-feedback-full (L3)  # 四类内容全量用户反馈
        ├── spec.md
        ├── design.md  # 可引用上级 design.md
        └── tasks.md   # F1–F16 子任务
```

当前 tasks.md 已含 F1–F16，是否拆子节点可按迭代粒度决定。
