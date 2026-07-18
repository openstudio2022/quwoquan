# Phase 3 验收凭证 — 小艺对话兴趣飞轮小循环（app_search 站内 → emergedTags → 推荐特征）

- 阶段：内容飞轮工程 Phase 3（小艺 `app_search` 接站内真实内容检索 + 对话浮现兴趣 `emergedTags` 反哺推荐特征）
- 状态：**P0 运行态实证 PASSED**；契约层已覆盖（T1/T2/Go 契约 + 端到端回流单测），T3-0 已用本地 Docker Mongo/Redis + 最新 host `content-service`/`assistant-service` 跑通真实 `search → app_search → emergedTags → assistant_interest → rm_recommend_feature` 全链路。
- 日期：2026-06-02
- 范围：T3-1 站内 app_search handler / T3-2 云侧 emergedTags 产出 / T3-3 端云行为契约 + 端侧回流接线
- 原则：不保留过往兼容、无 `v1/v2` 版本、metadata-first、单一真相源（项目未上线）

## 端到端飞轮链路（小循环）

```
用户 query
  → assistant-service ReAct loop
  → app_search (contentAppSearchHandler → content-service GET /content/posts/search)
  → 命中站内 posts（PostSearchItemView.categoryId / subCategory）
  → collectEmergedTags：categoryId/subCategory 去重归一 → Topic/<x> 路径制 tagRef
  → assistant.turn.completed envelope payload.emergedTags（List<String>）
  → 端 extractAssistantEmergedTags（只取 turn.completed、去重、过滤空值）
  → ContentBehaviorTracker.trackAssistantInterest(tagRefs)（不绑定 post）
  → BehaviorEvent{action: assistant_interest, tagRefs}
  → POST /content/behaviors
  → BehaviorBatchReported
  → RecommendFeatureProjector.onBehaviorBatch（对所有 event 的 tagRefs 累加，不区分 action）
  → userFeatures.tagInteraction.<tag> += 1
  → rm_recommend_feature → 下次召回/排序按 tagAffinities 反哺
```

## 任务与交付

| 任务 | 内容 | 产物 |
|---|---|---|
| T3-1 | 站内 `app_search` handler（替代外部搜索，命中站内内容） | `assistant-service/cmd/api/main.go`：`contentAppSearchHandler(baseURL,timeoutMs)` HTTP 调 content-service search；`buildSearchRegistry` 优先内容检索、回退既有 handler；`config.ContentSearch`/`contentSearchCfg`；`configs/default`(base_url:"") + `configs/alpha`(base_url:`http://127.0.0.1:18080`) `content_search` 段 |
| T3-2 | 云侧从 app_search 结果抽取 `emergedTags` 并随 `turn.completed` 下发 | `agent_loop.go`：`collectEmergedTags(result)`（categoryId/subCategory→`Topic/`、去重）+ `assistant.turn.completed` payload `+emergedTags`；`agent_loop_emerged_tags_test.go`（命中汇总 + 空结果不伪造）；`content.SearchPosts` 的 category/subCategory 必须优先由内容 `tagRefs` 的 `Topic/*` 派生，不能依赖请求回填 |
| T3-3 后端契约 | metadata-first 新增 `assistant_interest` 行为 + 三方一致 | `behaviors.yaml`：`assistant_interest`（`payload_fields:[tagRefs]`、`signal_weight:1.6`、不绑 post）；`hotpath.go` `SignalWeights["assistant_interest"]=1.6`；`behavior_repository.dart` `BehaviorAction.assistantInterest('assistant_interest')`；codegen 模板按 `payload_fields` 是否含 `postId` 决定参数 → `trackAssistantInterest(List<String> tagRefs)`（去掉错误的 postId） |
| T3-3 端侧接线 | turn.completed emergedTags → 行为回流 | `content_behavior_tracker.dart` `trackAssistantInterest(tagRefs)`（contentId 空、去重过滤空）；`personal_assistant_stream_controller.dart` 顶层 `extractAssistantEmergedTags(events)` + turn 完成钩子（`!failed` 时回流） |

## 关键决策（诚实记录）

1. **emergedTags 端云载体（D1 → 方案 X）**：云侧填进 `assistant.turn.completed` 流式 envelope 的 `payload['emergedTags']`（`AssistantStreamEventWire.payload` 是自由 `Map<String,dynamic>`，端侧直读，无需改 schema）。放弃方案 Y（注入 `AssistantTurnDiagnostics`/`RunArtifacts` 模型产物载体）——后者 `buildLongTermPreferenceFacts`/`diagnosticsEmergedTagMaps` 端侧本就**无调用方**，链路断裂，且需改动模型产物注入路径。
2. **`assistant_interest` 不绑 post（D2 → 改 codegen）**：`behaviors.yaml` `payload_fields:[tagRefs]` 明确不含 `postId`，但旧 codegen 模板对**所有**事件硬编码注入 `String postId` 参数 + `'postId': postId`。改模板为「按 `payload_fields` 是否含 `postId` 决定」（核对：除 `assistant_interest` 外其余 12 个事件首项均为 `postId`，变更只影响 `assistant_interest`，无现存调用方），符合 metadata-first。
3. **云侧无需为 `assistant_interest` 写特殊分支**：`RecommendFeatureProjector.onBehaviorBatch` 对每个 event 的 `tagRefs` 一视同仁累加进 `tagInteraction`（`recommend_feature.go:145`），不依赖 `contentId`、不区分 `action` → `assistant_interest` 的 `tagRefs` 天然进 `rm_recommend_feature`。`RawBehaviorEvent.Action` 读 `action` 字段，与端 `BehaviorEvent.toJson()` 的 `action` 一致。
4. **两套同名 tracker 的取舍**：UI 走手写实例 `core/trackers/ContentBehaviorTracker`（经 `contentBehaviorTrackerProvider` 注入 `BehaviorRepository`，wire 字段 `action`、接 content-service），而非 generated static `ContentBehaviorTracker`（wire `type`，走 `BehaviorTrackerHttpClient`）。

## gate-out 校验

| 校验 | 命令 | 结果 |
|---|---|---|
| 云侧 emergedTags 契约 | `go test ./internal/application/ -run EmergedTags`（assistant-service） | ok（命中汇总去重 + 空结果不伪造） |
| 端云行为 action 一致性 | `python3 quwoquan_service/scripts/recommendation/verify_behavior_action_consistency.py` | OK（behaviors.yaml ↔ Go SignalWeights ↔ Dart BehaviorAction 三方一致） |
| codegen 幂等 | `make codegen-app` | `trackAssistantInterest(List<String> tagRefs)`（payload 仅 `type`+`tagRefs`，无 postId） |
| 端 tracker + 回流 | `flutter test test/local_contract/cloud/content/content_behavior_tracker__local_contract_test.dart test/local_contract/ui/assistant/personal_assistant_stream_controller__local_contract_test.dart` | All tests passed（33/33） |
| 端侧接线静态分析 | `dart analyze`（接线 3 文件） | 0 error/warning（仅 5 个 pre-existing info 级 lint） |

## 分层测试映射

- **T1（契约/codegen）**：`verify_behavior_action_consistency.py` 三方一致；codegen 幂等产出 `trackAssistantInterest(List<String>)`。
- **T2（单元）**：
  - 云侧 `agent_loop_emerged_tags_test.go`：app_search 命中 → `Topic/` 去重；无结果不伪造。
  - 端侧 `content_behavior_tracker_test`：`assistant_interest` 回流 tagRefs（去重过滤空、contentId 空、`toJson.action=assistant_interest`）、全空不上报。
  - 端侧 `personal_assistant_stream_controller_test`：`extractAssistantEmergedTags` 仅取 turn.completed 并去重过滤空。
- **端到端回流（端侧集成）**：`personal_assistant_stream_controller_test`：注入 `turn.completed{emergedTags}` → send → flush → `MockBehaviorRepository.recorded` 含单条 `assistant_interest{tagRefs}`；无 turn.completed 时不回流。
- **T3（运行时灌库实证）**：见末节（gate-out 必过）。

## 字段与一致性契约（已冻结）

- `behaviors.yaml.assistant_interest`：`payload_fields:[tagRefs]`、`signal_weight:1.6`、`ml_signal:moderate_positive`、`trigger:assistant_turn_emerged_tags`，**不携带 postId**。
- `emergedTags`：路径制 `Topic/<categoryId|subCategory>`；端云载体 = `assistant.turn.completed` envelope `payload.emergedTags`（`List<String>`）。
- 端 `BehaviorEvent{action:'assistant_interest', tagRefs:[...]}`，`contentId` 允许为空；云 `RawBehaviorEvent.Action` 读 `action`；`onBehaviorBatch` 读 `tagRefs` → `userFeatures.tagInteraction`。
- `SignalWeights["assistant_interest"]=1.6`（HotPath 实时信号权重）与 `behaviors.yaml` 同步。

## T3-0 运行时灌库实证（gate-out 必过，已通过）

**为何必须阻断**：Phase 3 的产品目标不是“分段可测”，而是“站内真实内容被小艺消费并反哺推荐特征”。因此必须在本地/CI 集成环境证明：导入后的运行库内容可被在线 search 召回，`app_search` 结果携带由内容 `tagRefs` 派生的 `categoryId/subCategory`，`turn.completed.payload.emergedTags` 非空，端侧/云侧可上报 `assistant_interest`，最终 `rm_recommend_feature.userFeatures.tagInteraction` 出现对应增量。

**本地实证结果（2026-06-02）**：
- 数据：alpha sample bundle 导入本地 Docker Mongo 默认运行库，`posts=659`、`entities=359`、`rm_discovery_feed=659`。
- 在线 search：`/content/posts/search?query=四川大学攻略指南` 命中 `posts/article/攻略/四川大学攻略指南/1`，返回 `categoryId=旅行`、`subCategory=旅行主题`。
- 小艺 app_search：自然语言 query `站内查找四川大学攻略指南` 经 query 归一化使用 `四川大学攻略指南` 命中 1 条站内内容。
- emergedTags：`conversationId=acv_01KT3X8090XT4PZYWQBSE371R8`，`turnId=atn_01KT3X8090SNHY9RS5CBCMC0R1`，`turn_completed.payload.emergedTags=[Topic/旅行, Topic/旅行主题]`。
- 行为回流：`POST /content/behaviors` 上报 `assistant_interest` 返回 `204`。
- 推荐特征：`rm_recommend_feature.userFeatures.tagInteraction` 包含 `Topic/旅行` 与 `Topic/旅行主题`。

**复现命令（待本地 docker/环境执行）**：

```bash
# 1. 起 Mongo（replSet）
docker compose -f quwoquan_ops/environments/compose/docker-compose.yaml up -d mongodb mongo-init

# 2. 灌库（复用 Phase 2 已验证的 Path A importer 与 P1 真实 publish）
go run ./services/content-service/cmd/import \
  --publish-root <canonical publish 根> --release-root <immutable release 根>

# 3. 起 content-service（连本地 Mongo），监听 18080
go run ./services/content-service/cmd/api

# 4. 直连验证 search endpoint 返回真实文章
curl 'http://127.0.0.1:18080/v1/content/posts/search?query=稻城亚丁'

# 5. 起 assistant-service（configs/alpha 已配 content_search.base_url=18080）
go run ./services/assistant-service/cmd/api
#    向小艺发「稻城亚丁什么时候去最好」→ 观测 assistant.turn.completed.payload.emergedTags
#    端侧 trackAssistantInterest → POST /content/behaviors → 查 rm_recommend_feature.tagInteraction
```

## 结论与后续

- [x] T3-1 站内 app_search handler（编译通过、配置就位）。
- [x] T3-2 云侧 collectEmergedTags + turn.completed 下发 + 契约测试。
- [x] T3-3 后端契约三方一致（metadata/Go/Dart）+ codegen 模板修正（postId 不再误注入）。
- [x] T3-3 端侧接线 + 端到端回流单测（33/33 全绿）。
- [x] 端云三段链路逐段验证；云侧消费天然支持（无需为 assistant_interest 写特殊分支）。
- [x] T3-0 运行时灌库实证（gate-out）：本地起 content-service + 有货 Mongo，跑通在线 search → 小艺 app_search → emergedTags → behaviors → tagInteraction 全链。
