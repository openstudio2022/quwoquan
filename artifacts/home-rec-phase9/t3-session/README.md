# 首页推荐商用化 · 阶段9 · T3 鉴权会话级端到端证据

> 生成时间：2026-06-19（UTC+8）· 环境：gamma-local · 验证方式：curl / HTTP 级真实集成
> 不构建/修改 Flutter app 代码；不放宽门禁；不触碰 `quwoquan_data/site_supply` 未提交改动。

## 0. 环境与前置动作

- gamma-local 全栈在跑（`stackctl health --target gamma-local --scope full` = 17/17 healthy，报告见
  `artifacts/stackctl/gamma/20260619T022920Z-health-gamma-local`）。
- **关键前置**：运行中的 `content-service` 镜像为 39h 前构建，早于「首页推荐归因闭环」提交（`c613f256`），
  其 `/v1/content/feed` envelope **不含** `feedRequestId / rankingVersion / reasonVersion`。
  本次从当前已提交源码重建并重新部署 `content-service`（仅该服务，`--no-deps --force-recreate`），
  使 gamma-local 反映真实当前契约。其余服务仍为既有构建。
  - 重建：`docker compose -f quwoquan_service/docker-compose.gamma-local.yaml build content-service`
  - 重部署：`docker compose -f quwoquan_service/docker-compose.gamma-local.yaml up -d --no-deps --force-recreate content-service`

### 端口（gamma-local，供 T4 复用）

| 角色 | 宿主端口 | 说明 |
|---|---|---|
| 边缘代理 gamma-proxy(Caddy) | 19000 (http) / 19100 (media) / 443 | `/v1/content` `/v1/user` `/v1/me` 等转发；**`/v1/auth/*` 未路由** |
| content-service | 19220 | feed / behaviors / `/metrics`（本次已重建） |
| user-service | 19210 | `/v1/auth/*` 直连 |
| chat-service | 19200 | |
| rec-model-service | 19240 | |
| redis | 19420 | |
| mongodb | 19410 | |
| postgres | 19400 | |
| elasticsearch | 19430 | |

## 1. 会话建立

gamma-local **无 OTP/integration provider**（`/v1/auth/otp/send` → `USER.AUTH.otp_provider_failed`，
依赖 `integration-service.local`，未在本地拓扑），社交登录同理。**唯一可用的真实会话路径 = anonymous device login**：

```bash
curl -sS -X POST http://127.0.0.1:19210/v1/auth/login/anonymous \
  -H 'Content-Type: application/json' \
  -d '{"installId":"t3-session-install-01","deviceFingerprintHash":"t3sessionfphash01","platform":"ios","appVersion":"1.0.0"}'
```

- 返回真实 JWT `accessToken` + `ownerId` + `activeSub.subAccountId=us_01_3278_01kvevr8s7s3b0arr7x3p27efe`（脱敏存证：`01_login_redacted.json`、`01_jwt_claims.json`）。
- 鉴权门控对照（`02_auth_gate.json`）：`GET /v1/content/footprint` 游客 **401** / 会话 **200**。
- 架构说明：gamma-local 无 token 校验型 API 网关；边缘 Caddy 透传 `Authorization` 与 `X-Client-User-Id`，
  content-service 以**身份头存在性**授权 auth-required 端点（与 App 客户端实际行为一致）。

## 2. T3 会话级证据矩阵

| 子项 | 结果 | 关键证据 |
|---|---|---|
| **envelope `feedRequestId`** | ✅ PASS | 会话 feed `feedRequestId=frq_01KVEWCA5EAWVW6ZW8MYC7TK6Z`（`03_envelope_assert.json`） |
| **envelope `rankingVersion`** | ✅ PASS | `rankingVersion=rec-v1`（+`reasonVersion=reason-v1`） |
| **envelope `intersectionReasons`** | ⚠️ 证据缺口（数据） | 全部 item `intersectionReasons` 为空；`follow_edges=0`、`rm_viewer_object_intersection` 缓存均 `reasonsJson="[]"`、`intersections/summary.totalCount=0`（`07_intersection_gap_evidence.txt`）。**契约字段已存在且已接线，仅 gamma-local 无交集/社交图种子数据**。 |
| **负反馈未来窗口 · hide_author** | ✅ PASS | 上报 `hide_author(alpha_moment_author)` 后连续 3 次 feed 该作者计数=0；`rec:hidden_authors:{us_01_3278...}` 含该作者（`04c_redis_hidden.txt`、`04_feed_after_*.json`） |
| **负反馈未来窗口 · hide_content_type** | ✅ PASS | 上报 `hide_content_type(image)` 后该类型计数=0；`rec:hidden_types:{us_01_3278...}` 含 `image` |
| **负反馈未来窗口 · dislike 单条** | ⚠️ 证据缺口（缺陷） | 被 dislike 的 `alpha_video_portrait_playable` 仍出现在 feed；但 `rec:negative:{us_01_3278...}` **已含**该 post（服务端已记录）。根因见 §4。 |
| **realtime patch 发射** | ✅ PASS（服务端指标） | `recommendation_feed_patch_emitted_total{patch_type="negative_feedback_removal",...}` 增量 +3（dislike/hide_author/hide_content_type 各 +1），并附带 `refresh_suggestion{reason="session_fatigue"}`（单批 3 条负反馈触发疲劳启发式）。`04/05_metrics_*.txt` |
| **realtime patch 外部订阅** | ⚠️ 证据缺口（基础设施） | `realtime-gateway` 在 gamma-local 未实现（compose profile `edge-media-pending`，无源码/Dockerfile）；且 content-service `realtime` redis scene = **进程内内存**（容器仅注入 `CONTENT_REDIS_REC/GENERAL_ADDR`，代码不读 `realtime` env）。故对共享 redis `PSUBSCRIBE rt:rec:feed:user:*` 仅见订阅确认、无 message（`05_redis_psubscribe.txt`）。patch 在进程内发射，证据以服务端指标为准。 |

## 3. 每步命令

完整可复现脚本：`run_t3_session.sh`（即「每步命令」记录）。要点：

```bash
# 会话 header
AUTH=(-H "Authorization: Bearer $TOKEN" -H "X-Client-User-Id: $SUB" -H "X-Client-Session-Id: $SESSION")

# envelope（会话态）
curl -sS "${AUTH[@]}" "http://127.0.0.1:19000/v1/content/feed?sort=recommend&limit=20"

# 负反馈（带 feedRequestId / position / channelId / referralSource，符合 behaviors.yaml common_fields）
curl -sS -X POST "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d '{"userId":"<SUB>","events":[{"type":"hide_author","postId":...,"authorId":...,"feedRequestId":...,"position":...,"channelId":"recommend","state":"negative",...}]}' \
  "http://127.0.0.1:19000/v1/content/behaviors"

# 再取 feed 断言收敛 + 服务端 patch 指标
curl -sS "${AUTH[@]}" "http://127.0.0.1:19000/v1/content/feed?sort=recommend&limit=50"
curl -sS "http://127.0.0.1:19220/metrics" | grep recommendation_feed_patch_emitted_total
```

## 4. 发现的缺陷 / 缺口（根因 + 复现）

1. **dislike 单条负反馈在 feed「仓库兜底分页」路径未生效**（推荐缺陷）
   - 根因：`Engine.LoadFeedbackExclusions` 仅当 `e.sessions` 实现 `NegativeFeedbackReader` 才装载
     `NegativeContentIDs`；而 `e.sessions` 是 `*SessionCache`，**未转发** inner `*HotPath` 的
     `NegativeContentIDs`；同时 `SessionState.NegativeIDs` 在两条 `getSessionState*` 里恒为 `nil`。
     → 召回管线（`FilterCandidates` 读 `rec:negative:`）会过滤 dislike，但 `feed_service.go` 的
     repository fallback（`appendPost`）拿到的 `NegativeContentIDs` 恒空。gamma-local 候选池薄、
     fallback 占多数，故 dislike 的单条剔除不可见。
   - 复现：dislike 某 post → `rec:negative:{user}` 含该 post，但 `GET /v1/content/feed?limit=50` 仍返回它。
2. **anonymous 账号创建唯一约束冲突**（user-service 缺陷）
   - 现象：`POST /v1/auth/login/anonymous`（新 install）→ `USER.SYSTEM.internal_error: create profile:
     duplicate key value violates unique constraint "user_profiles_phone_key"`。空手机号唯一约束导致
     **整库只能成功创建一个 anonymous 账号**；恢复同设备账号正常。
3. **intersection / 社交图种子未注入 gamma-local**（数据缺口）
   - `follow_edges=0`、viewer-object 交集缓存全空 → `intersectionReasons` 无源可填。

> 以上 3 项均为**新发现的长期风险**。按仓库规则，未经你确认前**未登记** `docs/outstanding_risks_backlog.md`。

## 5. 对照商用准出（T3 相关）

`docs/recommendation-commercial-maturity-plan.md` §7 T3 / T4：「明确负反馈后未来窗口收敛」
- 作者维度 / 内容类型维度：**达成**（gamma-local 真实 HTTP 证明）。
- 单条内容维度（dislike/not_interested）：**未达成**（fallback 路径缺口，§4.1）。
- realtime patch：服务端发射**达成**（指标）；端到端订阅链路**未达成**（realtime-gateway 未实现）。
- 个性化交集解释（intersectionReasons）：契约就绪，**数据未注入**，gamma-local 无法证明非空。

## 6. 文件索引

- `01_login_*.json` 会话（脱敏）/ `01_jwt_claims.json` JWT claims
- `02_auth_gate.json` 鉴权门控
- `03_feed_guest.json` / `03_feed_session_p1.json` / `03_envelope_assert.json` envelope
- `04_behaviors_request.json` / `04_behaviors_response.json` / `04_feed_after_{1,2,3}.json` 负反馈与收敛
- `04c_redis_negative.txt` / `04c_redis_hidden.txt` redis 侧记录证据
- `05_metrics_before.txt` / `05_metrics_after.txt` patch 发射指标 / `05_redis_psubscribe.txt` 订阅捕获
- `06_t3_matrix.json` 机器可读判定矩阵
- `07_intersection_gap_evidence.txt` 交集数据缺口证据
- `run_t3_session.sh` 一键复现脚本
- `08_dislike_fallback_regression.sh` + `08_*` 任务1（dislike 单条 fallback 收敛）回归证据
- `09_intersection_seed_regression.sh` + `09_*` 任务2（交集种子 → intersectionReasons 非空）回归证据

## 7. 本轮收口（任务1：dislike 单条 fallback 缺陷修复）

> 时间 2026-06-19（UTC+8）· 环境 gamma-local · content-service 已重建重部署
> （镜像 `localhost/quwoquan_service_content-service:latest` = `sha256:af8610ba3c0d…`，仅该服务 `--no-deps --force-recreate`）。

- **真因**（与 §4.1 一致）：生产读路径 `engine.sessions` 是 `*SessionCache`（包裹 `*HotPath`），
  而 `*SessionCache` **未实现** `NegativeFeedbackReader`，导致 `Engine.LoadFeedbackExclusions` 的
  `e.sessions.(NegativeFeedbackReader)` 断言失败、`FeedbackExclusions.NegativeContentIDs` 恒空；
  `feed_service.go` 的仓库兜底分页（`appendPost`）据此不剔除 dislike 单条内容。召回路径有
  `ExposureFilter`（读 `rec:negative:`）兜住，fallback 路径无人兜 → 薄候选池下 disliked post 漏出。
- **修法（fix-forward，单一真相源，R10 存储无关）**：在 `runtime/recommendation/session_cache.go`
  给 `*SessionCache` 增加 `NegativeContentIDs` 转发（沿用其既有 `RecordServed/FilterCandidates` 等
  转发同构），转发到 inner `*HotPath`（读 `rec:negative:{user}`）。`*SessionCache` 因此实现
  `NegativeFeedbackReader`，召回与 fallback 两路径收敛到同一真相源，不新造第二真相源。
- **Go 测试（T2，全绿；均为真回归：去除修复即 FAIL）**：
  - `runtime/recommendation`：`TestSessionCache_NegativeContentIDs_ForwardsToInner`、
    `TestEngine_LoadFeedbackExclusions_FallbackPath`（生产接线 SessionCache⊃HotPath 下 dislike/report/hide 均进 exclusions）；
    编译期 `var _ NegativeFeedbackReader = (*SessionCache)(nil)`。
  - `content-service/internal/application`：`TestListFeed_FallbackPath_FiltersDislikedContent`
    （空召回源强制走仓库 fallback，dislike 内容不得出现）。
  - `go test ./runtime/recommendation/... ./runtime/recpolicy/... ./services/content-service/...` 全绿。
- **gamma 回归（`08_*`）**：会话 dislike `alpha_video_landscape_playable` → `rec:negative:{us_01_3278…}` 含该 post →
  连续 3 次 `limit=50` feed（触达兜底分页）该 post 不再出现（`08_dislike_fallback_matrix.json`
  `dislike_single_post_removal_fallback_path=PASS`）；该用户全部 4 条历史负反馈（含 §4.1 记录的、修复前持续漏出的
  `alpha_video_portrait_playable`）在 3 次抓取中均 0 泄漏；`negative_feedback_removal` patch 指标 +1。

## 8. 本轮收口（任务2：env-seed-first 注入交集种子 → intersectionReasons 非空）

- **缺口定位**：feed 交集来自 `IntersectionService.Feed` → `ReadModelIntersectionSource` →
  `MongoIntersectionSource.FactReasons/AffinityReasons`，读 **content-service 自身库 `quwoquan_content`** 的
  `follow_edges` / `rm_recommend_feature` / `rec_learning_events` / `rm_discovery_feed` 读模型。
  gamma-local 实测 `quwoquan_content` **无 `follow_edges`/`circle_members` 集合**（posts=720、rm_discovery_feed=661 已seed，
  但社交图读模型为空）。真实部署里这些读模型由 user-service 关注事件跨服务投影产出，gamma-local 未接线该投影
  → `follow_edges=0` → 交集计算无源 → `intersectionReasons` 恒空。**这是 seed 通道缺失，非契约缺陷。**
- **最小正规扩展点（env-seed-first，单一真相源 fixture + 幂等 applier）**：
  - fixture：`quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json`
    （为会话 viewer 声明关注边 + 关注对象兴趣特征；含两个共享兴趣标签 `Topic/旅行/露营` 的真实作者 followee）。
  - applier：`quwoquan_service/scripts/seed/apply_content_social_graph_seed.py`
    （幂等向 `quwoquan_content` upsert `follow_edges` + `rm_recommend_feature.userFeatures.tagInteraction`，
    并失效 viewer 的 `rm_viewer_object_intersection` 预物化快照以触发回算）。
  - **未在 UI/脚本硬塞第二套业务数据**：种子唯一真相源是 metadata/test_fixtures 内的 fixture；applier 只读消费。
  - **anonymous 唯一约束冲突无关**：本路径直接 seed content-service 的 `follow_edges` 读模型（followee 为既有真实作者），
    不创建 user-service 账号，故 §4.2 的 `user_profiles_phone_key` 冲突不构成阻碍。
- **gamma 回归（`09_*`）**：应用种子后，鉴权会话 `GET /v1/content/feed?limit=50` 中 **12/50** item 的
  `intersectionReasons` 非空，`primaryText="你关注的人也在讨论这些主题"`（fact / dimension=relationship /
  source=followEdge），契约符合 70/20/10 light 配比；`/v1/content/intersections/summary` `totalCount=1`（relationship）；
  回算后 `rm_viewer_object_intersection` 快照非空（`09_intersection_matrix.json`
  `checkA_envelope_intersectionReasons=PASS`、`intersectionReasons_semantics_ok=true`）。
- **剩余整合项（非伪造，明确后续）**：该 fixture 尚未接入 gamma 标准 bring-up（现 gamma 业务数据由
  `quwoquan_service/scripts/seed/shared_pool_real_asset_pipeline.py` 装载，本轮按要求未触碰其未提交改动）。
  长期正解是 user-service 关注事件 → content-service `follow_edges` 读模型的跨服务投影；在其落地前，
  本 fixture + applier 即该读模型的最小正规替身，复现命令：
  `python3 quwoquan_service/scripts/seed/apply_content_social_graph_seed.py`。
