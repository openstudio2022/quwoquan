# Phase 2 验收凭证 — 端云桥：ship 内容打通发现流召回 + 溯源/条件画像贯通

- 阶段：内容飞轮工程 Phase 2 **A 组**（云侧 `content-service` + 端 `behavior`，与 Phase 1 `quwoquan_data` 并发）
- 状态：**A 组 PASSED + 真实内容灌库端到端已验证**；Phase 3 准入硬条件 1–4 满足（详见末节判定）；B 组残留项（旅行实体 `conditionProfile` 落盘 + manifest `authorId/coverUrl/publishedAt`）随 P1 收口，**不阻断 Phase 3 准入**
- 日期：2026-06-02（真实灌库验证时 P1 已产出 publish ≈ 6.6k posts / 3.3k entities）
- 范围：T2-1 metadata 真相源 / T2-2 Path A loader 丢弃修复 / T2-3 打通 `rm_discovery_feed` / T2-5 端 behavior `tagRefs`
- 原则：不保留过往兼容、无 `v1/v2` 版本、统一切新方案（项目未上线）

## 任务与交付

| 任务 | 内容 | 产物 |
|---|---|---|
| T2-1 | metadata 真相源加 `sourceTaskId`/`conditionProfile` | `fields.yaml`(Post `+sourceTaskId`)、`events.yaml`(PostCreated/PostPublished payload `+sourceTaskId`)、`discovery_feed.yaml`(顶层 fields + `client_projection` `+sourceTaskId`/`+conditionProfile`)；codegen 产出 `post.go.SourceTaskId`、`feed_item_dto.g.dart`（`sourceTaskId:String?` + `conditionProfile:Map<String,dynamic>?`） |
| T2-2 | 修 Path A loader 丢弃 bug | `cmd/import/loader.go`：`postManifest+SourceTaskId`、`entityFile+ConditionProfile/SourceTaskId`、`PostDoc`/`EntityDoc` 落字段；`main.go` `UpsertPosts`/`UpsertEntities` `$set` 落 `posts`/`entities` |
| T2-3 | 打通 ship→`rm_discovery_feed` | `cmd/import` 新增 `UpsertDiscoveryFeed`（同写发现流 ReadModel，`conditionProfile` 从主实体 join 冗余）；`DiscoveryFeedProjector.syncPost`、`BulkImportItem`、`UpsertDiscoveryFeedItem` 三处 `$set` 字段一致 |
| T2-5 | 端 behavior `tags`→`tagRefs` | `behavior_repository.dart` 发送(169)/重放(566) wire key 改 `tagRefs`，直接切换不留旧键 |

## 关键修正（诚实记录）

1. **importer 路径误解纠正**：ship（Path A，`cmd/import`）原只写 `posts`/`entities`，与 `rm_discovery_feed`（`tag_recall`/`hot_recall`/`explore_recall`/`author_recall`/`vector_recall` 的主真相源）**解耦** → 冷启动内容召回不到。本阶段 `cmd/import` 同写 `rm_discovery_feed`，`postId` 用稳定 `postRef`，`status/visibility` 固定 `published/public` 保证可召回。
2. **`rm_discovery_feed` 投影为手写 `bson.M`（非 codegen）** → `DiscoveryFeedProjector.syncPost` 手改，并与 `BulkImportItem`/`UpsertDiscoveryFeedItem` 三处 `$set` 字段对齐。
3. **loader 丢弃 bug**：`postManifest`/`entityFile` 未解析 `sourceTaskId`/`conditionProfile`，落库前被丢；已补结构体 + 构造 + `$set`。
4. **端 behavior wire key 不一致**：端发送/重放用 `tags`，云侧 `BehaviorEventInput` 与 `behaviors.yaml` canonical 为 `tagRefs` → 直接改 wire key（不双发、不 fallback 旧本地队列）。

## gate-out 校验

| 校验 | 命令 | 结果 |
|---|---|---|
| metadata 校验 | `make -C quwoquan_service verify-metadata` | PASS（69 实体 / 94 枚举） |
| codegen 幂等 | `make -C quwoquan_service codegen-content-service` / `codegen-app` 再跑 | `post.go` 5/0、`feed_item_dto.g.dart` 12/0（稳定无新 diff） |
| import 单测 | `go test ./services/content-service/cmd/import/...` | ok（含 `TestConditionProfileIndex`） |
| import mongo 集成 | `QWQ_TEST_MONGO_URI=… go test … -run Mongo`（临时 `mongo:7`） | 6 PASS（含 `TestMongoUpsertDiscoveryFeed`） |
| recommendation 投影 | `go test …/internal/infrastructure/recommendation/...` | ok（projector 改动不回退） |
| content-service 编译 | `go build ./services/content-service/...` | exit 0 |
| 端 behavior 契约 | `flutter test test/local_contract/cloud/behavior/contract/behavior_repository_contract__local_contract_test.dart` | All tests passed（含 `toJson 使用 tagRefs wire key`） |
| **真实灌库端到端 api_integration（历史证据）** | 当前命令为 `cmd/import --publish-root <canonical publish> --release-root <immutable release>` 灌临时 `mongo:7`；旧 sample-bundle 入口已退役 | 历史基线 `posts` 659/659、`rm_discovery_feed` 659、`entities` 359/359；新 release-first 契约由 importer local_contract 与临时 Mongo 复验 |

## 分层测试映射

- **T1（契约/codegen）**：`verify-metadata` + codegen 幂等；`post.go.SourceTaskId`、`feed_item_dto` 两字段。
- **T2（单元）**：`loader_test`（manifest→`PostDoc.SourceTaskId`、`_entity.json`→`EntityDoc.ConditionProfile`）、`conditionProfileIndex`。
- **T3（集成）**：`mongo_import_test.TestMongoUpsertDiscoveryFeed`（写 `rm_discovery_feed` + 主实体 `conditionProfile` join + `published/public`）。
- **端 serde**：`behavior_repository_contract_test`（`toJson` wire key `tagRefs`、无 `tags` 残留）。

## 字段与一致性契约（已冻结）

- `Post.sourceTaskId`：`string`、`NULLABLE`、`recommend_feature: true`（效果回流按 `sourceTask` 归因）。
- `rm_discovery_feed`：顶层 fields + `client_projection` 均含 `sourceTaskId(String?)` 与 `conditionProfile(Map<String,dynamic>?)`；`conditionProfile` 结构化子键 `{regions:[]string, seasons:[]string, altitudeMeters:int?}`。
- `events` `PostCreated`/`PostPublished` payload `+sourceTaskId`（在线 projector 透传；`conditionProfile` 为实体级，在线由绑定实体 `canonicalEntityId→entity.conditionProfile` 派生，payload 暂不携带，`$set` 键已就位向前兼容）。
- 三处 `rm_discovery_feed` 写入 `$set` 一致：`cmd/import.UpsertDiscoveryFeed` / `DiscoveryFeedProjector.syncPost` / `MongoBulkImportStore.UpsertDiscoveryFeedItem`。

## 与 Phase 1 并发边界

- **A 组（本凭证，已完成）**：仅触碰 `quwoquan_service`（content-service / metadata）+ `quwoquan_app`（behavior + codegen 产物），与 Phase 1 的 `quwoquan_data` 文件零交叉。
- **真实灌库验证（历史 P1 证据）**：旧 alpha 选择集曾以 659 posts / 359 entities 灌临时 `mongo:7` 跑通；当前选择集已归一为 immutable release `desired_state.json`，旧 sample bundle 文件与 importer 参数均已删除。
- **B 组残留项（随 P1 收口，均不阻断 Phase 3 准入）**：
  - `entities` 当前 `conditionProfile` 为 0（旅行实体未落 region/season；校园实体不需要）。`cmd/import.conditionProfileIndex` join 代码 + 单测/集成测试已就绪，待 P1 旅行实体落 `conditionProfile` 后地域/季节召回自然生效。
  - manifest 补 `authorId`/`coverUrl`/`publishedAt`：用于 feed 卡封面/作者展示与 `author_recall`；缺省**不阻断 `tag`/`hot`/`explore` 召回**。
  - `sourceTaskId` 属 object manifest 事实；release desired state/index 不复制该字段，loader 从自治对象读取。

## Phase 3 准入对照判定

Phase 3 = 小艺 `app_search` 接真实内容检索 + 兴趣 emergent tags 反哺推荐 + 客户端性能埋点。其准入硬条件即 Phase 2 准出：

| # | Phase 3 准入硬条件 | 状态 | 证据 |
|---|---|---|---|
| 1 | 内容溯源 `sourceTaskId` 贯通 metadata→Go→Dart→manifest→运行库 | ✅ | 三集合各 100% 带 `sourceTaskId` |
| 2 | ship 内容进入召回真相源 `rm_discovery_feed` 且可召回 | ✅ | 659 篇真实灌库全 `published/public` |
| 3 | 端云行为契约统一（`tagRefs`） | ✅ | T2-5 + 端 serde 契约测试 |
| 4 | 真实内容在召回库可被检索（小艺 `app_search` 前提） | ✅ | `rm_discovery_feed` 659 篇带 Topic/Entity/Format `tagRefs` |
| 5 | 旅行 `conditionProfile` 地域/季节召回 | ⚠️ 代码就绪/数据待 P1 | join 逻辑 + 测试通过；旅行实体 `conditionProfile` 待 P1 落盘（不阻断 Phase 3 主路径） |

**判定：硬条件 1–4 全部满足，第 5 项为非阻断增强项。Phase 2 准出达成，Phase 3 可准入。**

## 结论与后续

- [x] T2-1/2/3/5 A 组代码 + 分层测试（T1/T2/T3/端 serde）PASS。
- [x] `cmd/import` 同写 `rm_discovery_feed`，冷启动内容进入召回真相源（mongo 集成测试 + **真实灌库 659 篇端到端**双重证明）。
- [x] 端 behavior 上报 wire 契约与云侧统一为 `tagRefs`。
- [x] **Phase 3 准入硬条件 1–4 满足**，Phase 2 准出达成。
- [ ] 随 P1 收口：旅行实体 `conditionProfile` 落盘（开启地域/季节召回）；manifest 补 `authorId`/`coverUrl`/`publishedAt`（feed 卡封面 + `author_recall`）。
